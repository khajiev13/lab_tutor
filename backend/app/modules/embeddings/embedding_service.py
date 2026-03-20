from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI

from app.core.settings import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    _client: OpenAI
    _model: str
    _expected_dim: int | None

    def __init__(self) -> None:
        api_key = settings.embedding_api_key or settings.llm_api_key
        base_url = settings.embedding_base_url or settings.llm_base_url

        if not api_key:
            raise ValueError(
                "Missing embeddings API key. Set LAB_TUTOR_EMBEDDING_API_KEY "
                "or LAB_TUTOR_LLM_API_KEY."
            )

        self._expected_dim = settings.embedding_dims
        self._model = settings.embedding_model
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=settings.embedding_timeout_seconds,
            max_retries=0,  # We handle retries ourselves.
        )

    def embed_documents(
        self,
        texts: list[str],
        *,
        on_batch_done: Callable[[int, int], None] | None = None,
    ) -> list[list[float]]:
        """Embed a list of texts with internal batching + retries.

        Args:
            texts: Texts to embed.
            on_batch_done: Optional callback invoked after each batch with
                ``(embedded_so_far, total)``.
        """
        if not texts:
            return []

        batch_size = max(1, int(settings.embedding_batch_size))
        max_retries = max(0, int(settings.embedding_max_retries))
        base_sleep = float(settings.embedding_retry_base_seconds)
        max_workers = max(1, int(settings.embedding_parallel_workers))
        total = len(texts)

        # Build ordered list of (batch_index, batch_texts)
        batches = [
            (i, texts[start : start + batch_size])
            for i, start in enumerate(range(0, total, batch_size))
        ]

        if len(batches) <= 1 or max_workers <= 1:
            # Fast path: no parallelism needed
            all_vectors: list[list[float]] = []
            for _, batch in batches:
                vectors = self._embed_with_retries(
                    batch=batch,
                    max_retries=max_retries,
                    base_sleep_seconds=base_sleep,
                )
                all_vectors.extend(vectors)
                if on_batch_done is not None:
                    on_batch_done(len(all_vectors), total)
            self._validate_dims(all_vectors)
            return all_vectors

        # Parallel path: process batches concurrently
        results: dict[int, list[list[float]]] = {}
        embedded_so_far = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(
                    self._embed_with_retries,
                    batch=batch,
                    max_retries=max_retries,
                    base_sleep_seconds=base_sleep,
                ): idx
                for idx, batch in batches
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                vectors = future.result()  # propagates exceptions
                results[idx] = vectors
                embedded_so_far += len(vectors)
                if on_batch_done is not None:
                    on_batch_done(embedded_so_far, total)

        # Reassemble in original order
        all_vectors = []
        for i in range(len(batches)):
            all_vectors.extend(results[i])

        self._validate_dims(all_vectors)
        return all_vectors

    def _embed_with_retries(
        self, *, batch: list[str], max_retries: int, base_sleep_seconds: float
    ) -> list[list[float]]:
        attempt = 0
        kwargs: dict = {
            "model": self._model,
            "input": batch,
        }
        if self._expected_dim is not None:
            kwargs["dimensions"] = self._expected_dim

        while True:
            try:
                resp = self._client.embeddings.create(**kwargs)
                return [d.embedding for d in resp.data]
            except Exception as e:
                if attempt >= max_retries:
                    raise

                sleep_s = base_sleep_seconds * (2**attempt)
                # small jitter to avoid thundering herd
                sleep_s = sleep_s + random.uniform(0.0, max(0.1, sleep_s * 0.1))
                logger.warning(
                    "Embedding batch failed (attempt %s/%s): %s; retrying in %.2fs",
                    attempt + 1,
                    max_retries + 1,
                    str(e),
                    sleep_s,
                )
                time.sleep(sleep_s)
                attempt += 1

    def _validate_dims(self, vectors: list[list[float]]) -> None:
        if not vectors:
            return

        expected = self._expected_dim
        if expected is None:
            return

        for v in vectors:
            if len(v) != expected:
                raise ValueError(
                    f"Embedding dimension mismatch: expected {expected}, got {len(v)}"
                )

    # ── Concept deduplication helpers ────────────────────────────

    @staticmethod
    def find_similar_concept(
        session,
        *,
        concept_name: str,
        embedding: list[float],
        threshold: float | None = None,
        top_k: int = 5,
    ) -> dict | None:
        """Find the best matching existing CONCEPT via the Neo4j vector index.

        Returns ``{"name": ..., "score": ...}`` for the top match above
        *threshold*, or ``None`` if nothing qualifies.
        """
        if threshold is None:
            threshold = settings.concept_similarity_threshold

        record = session.run(
            "CALL db.index.vector.queryNodes('concept_embedding_idx', $top_k, $embedding) "
            "YIELD node, score "
            "WHERE score >= $threshold AND node.name <> toLower($concept_name) "
            "RETURN node.name AS name, score "
            "ORDER BY score DESC LIMIT 1",
            {
                "embedding": embedding,
                "threshold": threshold,
                "top_k": top_k,
                "concept_name": concept_name,
            },
        ).single()

        return {"name": record["name"], "score": record["score"]} if record else None

    def embed_and_dedup_concepts(
        self,
        session,
        new_concepts: list[dict],
        *,
        threshold: float | None = None,
    ) -> list[dict]:
        """Embed concept names and match each against existing graph concepts.

        Args:
            session: An open Neo4j session.
            new_concepts: List of dicts with at least ``"name"`` and
                optionally ``"description"``.
            threshold: Cosine similarity threshold override (defaults to
                ``settings.concept_similarity_threshold``).

        Returns a list of dicts (same length as *new_concepts*), each with:
            - ``action``: ``"merge"`` or ``"create"``
            - ``target_name``: concept name to link to
            - ``embedding``: vector (only when ``action == "create"``)
            - ``description``: original description (only when ``action == "create"``)
        """
        if not new_concepts:
            return []

        names = [c["name"].strip().casefold() for c in new_concepts]
        descriptions = [c.get("description", "") for c in new_concepts]
        vectors = self.embed_documents(names)

        results: list[dict] = []
        for name, desc, vec in zip(names, descriptions, vectors, strict=True):
            match = self.find_similar_concept(
                session,
                concept_name=name,
                embedding=vec,
                threshold=threshold,
            )
            if match is not None:
                results.append(
                    {
                        "action": "merge",
                        "target_name": match["name"],
                        "original_name": name,
                        "score": match["score"],
                    }
                )
            else:
                results.append(
                    {
                        "action": "create",
                        "target_name": name,
                        "embedding": vec,
                        "description": desc,
                    }
                )

        return results
