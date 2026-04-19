"""Flask route handlers for the ARCD inference service.

Endpoints
---------
GET  /health          — liveness + checkpoint status
GET  /info            — vocab metadata
POST /mastery         — per-skill mastery for one student
POST /predict         — P(correct) for target questions
POST /next-question   — recommend the next question to present
"""
from __future__ import annotations

from flask import Blueprint, Response, jsonify, request
from pydantic import ValidationError

from arcd_serving.app import get_registry
from arcd_serving.schemas import (
    MasteryRequest,
    MasteryResponse,
    NextQuestionRequest,
    NextQuestionResponse,
    PredictRequest,
    PredictResponse,
)

bp = Blueprint("arcd", __name__)


def _bad_request(msg: str) -> tuple[Response, int]:
    return jsonify({"error": msg}), 400


def _validation_error(exc: ValidationError) -> tuple[Response, int]:
    return jsonify({"error": "Validation error", "detail": exc.errors()}), 422


# ── GET /health ───────────────────────────────────────────────────────────────

@bp.get("/health")
def health() -> tuple[Response, int]:
    """Liveness probe — always 200, payload reflects model readiness."""
    reg = get_registry()
    return (
        jsonify(
            {
                "status": "ok" if reg.is_available else "degraded",
                "checkpoint_loaded": reg.is_available,
                "model_version": reg.model_version,
                "best_val_auc": reg.best_val_auc,
            }
        ),
        200,
    )


# ── GET /info ─────────────────────────────────────────────────────────────────

@bp.get("/info")
def info() -> tuple[Response, int]:
    """Return vocab metadata."""
    reg = get_registry()
    if not reg.is_available:
        return jsonify({"error": "Model not available"}), 503

    vocab = reg._vocab  # noqa: SLF001
    concept_names = list(vocab.get("concept", {}).keys())
    return (
        jsonify(
            {
                "n_skills": len(concept_names),
                "n_questions": len(vocab.get("question", {})),
                "n_students": len(vocab.get("user", {})),
                "concept_names": concept_names[:50],
                "device": "cpu",
            }
        ),
        200,
    )


# ── POST /mastery ─────────────────────────────────────────────────────────────

@bp.post("/mastery")
def mastery() -> tuple[Response, int]:
    """Return per-skill mastery scores for a student.

    Request body (JSON)
    -------------------
    ``interactions`` : list of ``{question_name, correct, timestamp_sec}``
    ``concept_names`` : optional list of skill names (defaults to all)
    ``seq_len``      : optional int (default 50)
    """
    reg = get_registry()
    if not reg.is_available:
        return jsonify({"error": "Model not available"}), 503

    try:
        body = MasteryRequest.model_validate(request.get_json(force=True) or {})
    except ValidationError as exc:
        return _validation_error(exc)

    concept_names = body.concept_names
    if concept_names is None:
        concept_names = list(reg._vocab.get("concept", {}).keys())  # noqa: SLF001

    interactions = [i.model_dump() for i in body.interactions]
    mastery_map = reg.predict_mastery(interactions, concept_names, seq_len=body.seq_len)

    return jsonify(MasteryResponse(mastery=mastery_map).model_dump()), 200


# ── POST /predict ─────────────────────────────────────────────────────────────

@bp.post("/predict")
def predict() -> tuple[Response, int]:
    """Return P(correct) for each target question.

    Request body (JSON)
    -------------------
    ``interactions``     : list of ``{question_name, correct, timestamp_sec}``
    ``target_questions`` : list of question names
    ``seq_len``          : optional int (default 50)
    """
    reg = get_registry()
    if not reg.is_available:
        return jsonify({"error": "Model not available"}), 503

    try:
        body = PredictRequest.model_validate(request.get_json(force=True) or {})
    except ValidationError as exc:
        return _validation_error(exc)

    interactions = [i.model_dump() for i in body.interactions]
    p_map = reg.predict_correctness(
        interactions, body.target_questions, seq_len=body.seq_len
    )

    predictions = [
        {"question_name": q, "p_correct": round(float(p), 6)}
        for q, p in p_map.items()
    ]
    return jsonify(PredictResponse(predictions=predictions).model_dump()), 200


# ── POST /next-question ───────────────────────────────────────────────────────

@bp.post("/next-question")
def next_question() -> tuple[Response, int]:
    """Recommend the next question from a candidate pool.

    Strategy ``max_uncertainty`` (default): picks the question whose
    P(correct) is closest to 0.5 — the item the model is most uncertain
    about, maximising information gain under 1-parameter IRT assumptions.

    Strategy ``max_information``: same heuristic but alias retained for
    future parametric IRT information functions.

    Request body (JSON)
    -------------------
    ``interactions``       : list of ``{question_name, correct, timestamp_sec}``
    ``candidate_questions``: list of question names to pick from
    ``strategy``           : ``"max_uncertainty"`` | ``"max_information"``
    ``seq_len``            : optional int (default 50)
    """
    reg = get_registry()
    if not reg.is_available:
        return jsonify({"error": "Model not available"}), 503

    try:
        body = NextQuestionRequest.model_validate(request.get_json(force=True) or {})
    except ValidationError as exc:
        return _validation_error(exc)

    if not body.candidate_questions:
        return _bad_request("candidate_questions must not be empty")

    interactions = [i.model_dump() for i in body.interactions]
    p_map = reg.predict_correctness(
        interactions, body.candidate_questions, seq_len=body.seq_len
    )

    # Sort by distance from 0.5 ascending (most uncertain first).
    ranked = sorted(p_map.items(), key=lambda kv: abs(kv[1] - 0.5))
    best_name, best_p = ranked[0]
    alternatives = [
        {"question_name": q, "p_correct": round(float(p), 6)} for q, p in ranked[1:]
    ]

    return (
        jsonify(
            NextQuestionResponse(
                recommended_question=best_name,
                p_correct=round(float(best_p), 6),
                alternatives=alternatives,
            ).model_dump()
        ),
        200,
    )
