"""Core pipeline: query generation, embedding filter, LLM scoring, coverage selection."""

from __future__ import annotations

import logging

import numpy as np
from openai import OpenAI

from app.core.settings import settings

from .schemas import (
    BatchResourceScores,
    CandidateResource,
    ProgressCallback,
    ResourceScore,
    SearchQueries,
    SkillProfile,
)
from .search_engines import search_for_skill

logger = logging.getLogger(__name__)

# ── LLM / Embedding clients (lazy singletons) ────────────────

_llm_client: OpenAI | None = None
_embed_client: OpenAI | None = None


def _get_llm_client() -> OpenAI:
    global _llm_client
    if _llm_client is None:
        _llm_client = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=120,
        )
    return _llm_client


def _get_embed_client() -> OpenAI:
    global _embed_client
    if _embed_client is None:
        _embed_client = OpenAI(
            api_key=settings.embedding_api_key or settings.llm_api_key,
            base_url=settings.embedding_base_url or settings.llm_base_url,
            timeout=120,
        )
    return _embed_client


def _chat(messages: list[dict], *, max_completion_tokens: int = 4096) -> str:
    resp = _get_llm_client().chat.completions.create(
        model=settings.llm_model,
        messages=messages,
        temperature=0,
        max_completion_tokens=max_completion_tokens,
    )
    return resp.choices[0].message.content or ""


def _embed_texts(texts: list[str], *, batch_size: int = 10) -> list[list[float]]:
    client = _get_embed_client()
    dims = settings.embedding_dims or 1536
    all_vectors: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        resp = client.embeddings.create(
            model=settings.embedding_model or "text-embedding-3-small",
            input=batch,
            dimensions=dims,
        )
        all_vectors.extend([d.embedding for d in resp.data])
    return all_vectors


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    min_len = min(len(a), len(b))
    a_arr, b_arr = np.array(a[:min_len]), np.array(b[:min_len])
    return float(
        np.dot(a_arr, b_arr) / (np.linalg.norm(a_arr) * np.linalg.norm(b_arr) + 1e-10)
    )


def _strip_json_fence(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return s


# ═══════════════════════════════════════════════════════════════
#  Pipeline stages
# ═══════════════════════════════════════════════════════════════


def generate_queries(
    skill: SkillProfile, system_prompt: str, user_message: str
) -> list[str]:
    """Generate 4-6 search queries for a single skill via LLM."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    raw = _chat(messages)
    parsed = SearchQueries.model_validate_json(_strip_json_fence(raw))
    return parsed.queries


def embedding_filter(
    skill: SkillProfile,
    candidates: list[CandidateResource],
    top_k: int = 20,
) -> tuple[list[tuple[CandidateResource, float]], dict[str, list[float]]]:
    """Coarse-rank candidates by cosine similarity to skill profile embedding."""
    if not candidates:
        return [], {}

    profile_text = skill.build_profile_text()
    candidate_texts = [f"{c.title}. {c.snippet}" for c in candidates]

    all_texts = [profile_text] + candidate_texts
    all_embeddings = _embed_texts(all_texts)

    profile_vec = all_embeddings[0]
    candidate_vecs = all_embeddings[1:]

    scored: list[tuple[CandidateResource, float]] = []
    url_to_embedding: dict[str, list[float]] = {}
    for candidate, vec in zip(candidates, candidate_vecs, strict=True):
        sim = _cosine_similarity(profile_vec, vec)
        scored.append((candidate, sim))
        url_to_embedding[candidate.url] = vec

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k], url_to_embedding


CONCEPT_SIM_THRESHOLD = 0.3


def _validate_concepts_covered(
    llm_concepts: list[str],
    concept_sims: dict[str, float],
    threshold: float = CONCEPT_SIM_THRESHOLD,
) -> list[str]:
    """Keep only LLM-claimed concepts where embedding similarity confirms relevance."""
    if not concept_sims:
        return llm_concepts
    return [name for name in llm_concepts if concept_sims.get(name, 0.0) >= threshold]


def _build_concept_list_for_prompt(skill: SkillProfile) -> str:
    lines = []
    for i, c in enumerate(skill.concepts, 1):
        desc = c.get("definition") or c.get("description") or ""
        if desc:
            lines.append(f'  {i}. "{c["name"]}" -- {desc}')
        else:
            lines.append(f'  {i}. "{c["name"]}"')
    return "\n".join(lines) if lines else "  (no concepts listed)"


def score_candidates(
    skill: SkillProfile,
    candidates: list[tuple[CandidateResource, float]],
    url_to_embedding: dict[str, list[float]],
    scoring_prompt: str,
    weights: dict[str, float],
) -> list[tuple[CandidateResource, ResourceScore, float]]:
    """Score candidates with LLM rubric + embedding alignment."""
    if not candidates:
        return []

    profile_text = skill.build_profile_text()
    concept_list = _build_concept_list_for_prompt(skill)
    candidates_text = "\n\n".join(
        f"[{i}] Title: {c.title}\n    URL: {c.url}\n    Domain: {c.domain}\n    Snippet: {c.snippet}"
        for i, (c, _sim) in enumerate(candidates)
    )

    messages = [
        {"role": "system", "content": scoring_prompt},
        {
            "role": "user",
            "content": (
                f"SKILL PROFILE:\n{profile_text}\n\n"
                f"SKILL CONCEPTS (use these EXACT names in concepts_covered):\n{concept_list}\n"
                f"Total concepts: {len(skill.concepts)}\n\n"
                f"CANDIDATES ({len(candidates)}):\n{candidates_text}\n\n"
                f"Score ALL {len(candidates)} candidates. Return exactly {len(candidates)} score objects."
            ),
        },
    ]

    raw = _chat(messages, max_completion_tokens=8192)
    batch = BatchResourceScores.model_validate_json(_strip_json_fence(raw))

    results: list[tuple[CandidateResource, ResourceScore, float]] = []
    for i, (candidate, _sim) in enumerate(candidates):
        if i >= len(batch.scores):
            break
        score = batch.scores[i]

        # Compute embedding alignment (mean cosine sim across all concept embeddings)
        emb_alignment = 0.0
        concept_sims: dict[str, float] = {}
        candidate_emb = url_to_embedding.get(candidate.url)
        if candidate_emb:
            for c in skill.concepts:
                emb = c.get("embedding")
                if emb is None:
                    continue
                concept_sims[c["name"]] = _cosine_similarity(candidate_emb, emb)
            if concept_sims:
                emb_alignment = sum(concept_sims.values()) / len(concept_sims)

        # Validate LLM concept claims
        score.concepts_covered = _validate_concepts_covered(
            score.concepts_covered, concept_sims
        )

        # Compute weighted final score
        final = (
            weights["recency"] * score.recency_score
            + weights["concept_coverage"] * score.concept_coverage_score
            + weights["embedding_alignment"] * emb_alignment
            + weights["pedagogy"] * score.pedagogy_score
            + weights["depth"] * score.depth_score
            + weights["extra"] * score.extra_score
        )
        results.append((candidate, score, final))

    results.sort(key=lambda x: x[2], reverse=True)
    return results


def select_coverage_maximizing(
    scored: list[tuple[CandidateResource, ResourceScore, float]],
    skill_concepts: list[str],
    top_k: int = 3,
    min_types: int = 2,
) -> list[tuple[CandidateResource, ResourceScore, float]]:
    """Select top-K resources that maximize total concept coverage using greedy set-cover."""
    if len(scored) <= top_k:
        return scored

    covered: set[str] = set()
    selected: list[tuple[CandidateResource, ResourceScore, float]] = []
    remaining = list(scored)

    while len(selected) < top_k and remaining:
        best_idx = 0
        best_new_count = -1
        best_final = -1.0

        for i, (_c, s, f) in enumerate(remaining):
            reading_concepts = set(s.concepts_covered)
            new_count = len(reading_concepts - covered)
            if new_count > best_new_count or (
                new_count == best_new_count and f > best_final
            ):
                best_idx = i
                best_new_count = new_count
                best_final = f

        pick = remaining.pop(best_idx)
        selected.append(pick)
        covered.update(pick[1].concepts_covered)

    # Diversity check: ensure at least min_types different resource types
    types_seen = {s.resource_type for _, s, _ in selected}
    if len(types_seen) < min_types and remaining:
        type_count: dict[str, int] = {}
        for _, s, _ in selected:
            type_count[s.resource_type] = type_count.get(s.resource_type, 0) + 1

        new_type_candidate = None
        for item in remaining:
            if item[1].resource_type not in types_seen:
                new_type_candidate = item
                break

        if new_type_candidate:
            swap_idx = None
            swap_score = float("inf")
            for i, (_c, s, f) in enumerate(selected):
                if type_count.get(s.resource_type, 0) > 1 and f < swap_score:
                    swap_idx = i
                    swap_score = f
            if swap_idx is not None:
                selected[swap_idx] = new_type_candidate

    return selected


# ═══════════════════════════════════════════════════════════════
#  Full pipeline for one skill
# ═══════════════════════════════════════════════════════════════


def process_single_skill(
    skill: SkillProfile,
    *,
    query_gen_system: str,
    query_user_message: str,
    scoring_system: str,
    weights: dict[str, float],
    blacklist_domains: set[str],
    exclude_sites: list[str],
    tavily_include_domains: list[str] | None,
    top_k: int = 3,
    progress: ProgressCallback | None = None,
) -> list[tuple[CandidateResource, ResourceScore, float]]:
    """Run the full discovery pipeline for a single skill."""

    def _progress(phase: str, detail: str = "") -> None:
        if progress:
            progress(phase, detail)

    # 1. Generate queries
    _progress("query_gen", f"Generating search queries for {skill.name}")
    queries = generate_queries(skill, query_gen_system, query_user_message)
    logger.info("Generated %d queries for skill %s", len(queries), skill.name)

    # 2. Search
    _progress("searching", f"Searching {len(queries)} queries across engines")
    candidates = search_for_skill(
        queries,
        blacklist_domains=blacklist_domains,
        exclude_sites=exclude_sites,
        tavily_include_domains=tavily_include_domains,
    )
    logger.info("Found %d unique candidates for skill %s", len(candidates), skill.name)

    if not candidates:
        return []

    # 3. Embedding filter
    _progress("filtering", f"Embedding filter on {len(candidates)} candidates")
    filtered, url_to_embedding = embedding_filter(skill, candidates)
    logger.info("Filtered to %d candidates for skill %s", len(filtered), skill.name)

    if not filtered:
        return []

    # 4. LLM scoring
    _progress("scoring", f"LLM scoring {len(filtered)} candidates")
    scored = score_candidates(
        skill, filtered, url_to_embedding, scoring_system, weights
    )
    logger.info("Scored %d candidates for skill %s", len(scored), skill.name)

    # 5. Coverage-maximizing selection
    _progress("selecting", f"Selecting top {top_k} resources")
    concept_names = [c["name"] for c in skill.concepts]
    final = select_coverage_maximizing(scored, concept_names, top_k=top_k)

    covered = set()
    for _, s, _ in final:
        covered.update(s.concepts_covered)
    coverage = len(covered & set(concept_names))
    total = len(concept_names)
    logger.info(
        "Skill %s: %d resources, %d/%d concepts covered (%.0f%%)",
        skill.name,
        len(final),
        coverage,
        total,
        coverage / max(total, 1) * 100,
    )

    return final
