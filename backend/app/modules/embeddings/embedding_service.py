from __future__ import annotations

import logging
import random
import time

from langchain_openai import OpenAIEmbeddings
from pydantic import SecretStr

from app.core.settings import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    _embeddings: OpenAIEmbeddings
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
        self._embeddings = OpenAIEmbeddings(
            model=settings.embedding_model,
            dimensions=settings.embedding_dims,
            api_key=SecretStr(api_key),
            base_url=base_url,
            # We handle retries ourselves to centralize logging + control.
            max_retries=0,
            chunk_size=settings.embedding_batch_size,
        )
        # Field exists on the pydantic model; setting it here avoids type-checker issues.
        self._embeddings.request_timeout = settings.embedding_timeout_seconds

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        batch_size = max(1, int(settings.embedding_batch_size))
        max_retries = max(0, int(settings.embedding_max_retries))
        base_sleep = float(settings.embedding_retry_base_seconds)

        all_vectors: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            vectors = self._embed_with_retries(
                batch=batch,
                max_retries=max_retries,
                base_sleep_seconds=base_sleep,
            )
            all_vectors.extend(vectors)

        self._validate_dims(all_vectors)
        return all_vectors

    def _embed_with_retries(
        self, *, batch: list[str], max_retries: int, base_sleep_seconds: float
    ) -> list[list[float]]:
        attempt = 0
        while True:
            try:
                return list(self._embeddings.embed_documents(batch))
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
