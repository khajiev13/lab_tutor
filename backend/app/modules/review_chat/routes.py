"""Interactive Review Chat — FastAPI routes.

Provides the same API surface as the original standalone RevFell chat server
so that the existing chat-tab.tsx can connect without modification (except for
the base URL and JWT auth headers).

Endpoints under /api/:
  GET  /api/health                  — service health
  POST /api/review/start            — start a review session
  GET  /api/review/session/{sid}    — check session liveness
  POST /api/review/next-question    — fetch next question
  POST /api/review/answer           — submit an answer
  POST /api/review/skip             — skip current question
  POST /api/review/hint             — get a progressive hint
  POST /api/review/explain          — explain the concept
  POST /api/review/chat/stream      — streaming chat during review (SSE)
  POST /api/review/practice-skill   — practice a specific skill
  POST /api/chat/stream             — general free-form chat (SSE)
"""

from __future__ import annotations

import contextlib
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from neo4j import Driver as Neo4jDriver

from app.core.neo4j import get_neo4j_driver
from app.core.settings import settings
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["review-chat"])

SESSION_TTL = 7200  # 2 hours


# ── Session state ─────────────────────────────────────────────────────────────


@dataclass
class ReviewSession:
    session_id: str
    user_id: int
    course_id: int
    skill_names: list[str]
    mastery: list[float]
    pco_skill_names: set[str]
    results: list[dict]
    current_question: dict | None
    progress: dict
    created_at: float
    hint_count: int = 0
    is_complete: bool = False
    thinking_mode: str = "fast"
    chat_history: list[dict] | None = None


_sessions: dict[str, ReviewSession] = {}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _cleanup_sessions() -> None:
    now = time.time()
    stale = [sid for sid, s in _sessions.items() if now - s.created_at > SESSION_TTL]
    for sid in stale:
        del _sessions[sid]


def _get_session(session_id: str, user_id: int) -> ReviewSession:
    sess = _sessions.get(session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    if sess.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not your session")
    return sess


def _parse_course_id(dataset_id: str) -> int:
    if dataset_id.startswith("course_"):
        try:
            return int(dataset_id[7:])
        except ValueError:
            pass
    raise HTTPException(status_code=400, detail=f"Invalid dataset_id: {dataset_id!r}")


def _mastery_difficulty(mastery: float) -> str:
    if mastery < 0.3:
        return "easy"
    if mastery < 0.6:
        return "medium"
    return "hard"


# ── LLM ───────────────────────────────────────────────────────────────────────


def _call_llm(prompt: str, *, max_tokens: int = 400, temperature: float = 0.7) -> str:
    from openai import OpenAI

    client = OpenAI(
        api_key=settings.llm_api_key or "no-key",
        base_url=settings.llm_base_url,
    )
    resp = client.chat.completions.create(
        model=settings.llm_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content or ""


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
    return json.loads(text)


def _generate_question(
    skill_name: str, mastery: float, is_pco: bool, q_num: int, q_total: int, thinking_mode: str
) -> dict:
    difficulty = _mastery_difficulty(mastery)
    pco = " This skill is challenging for the student — be encouraging." if is_pco else ""
    mode_instructions = (
        "FAST mode: Ask one concise question that can be answered in 2-4 sentences. "
        "Keep wording direct and practical."
        if thinking_mode == "fast"
        else "DEEP mode: Ask a multi-step reasoning question. "
        "Require explanation of why, not only what. Include a realistic scenario."
    )
    prompt = (
        f'Generate a {difficulty} review question for the skill: "{skill_name}".\n'
        f"Student mastery: {mastery:.0%}.{pco}\n"
        f"{mode_instructions}\n"
        "Respond with JSON ONLY (no markdown fences):\n"
        '{"question":"...","hint":"...","correct_answer":"...","explanation":"..."}'
    )
    try:
        data = _parse_json(_call_llm(prompt, max_tokens=400))
        return {
            "index": q_num,
            "total": q_total,
            "skill_name": skill_name,
            "difficulty": difficulty,
            "is_pco": is_pco,
            "question": data.get("question") or f"Explain the core concept of {skill_name}.",
            "hint": data.get("hint") or "Think about the definition and key principles.",
            "correct_answer": data.get("correct_answer") or "",
            "explanation": data.get("explanation") or "",
        }
    except Exception as exc:
        logger.warning("Question gen failed for %s: %s", skill_name, exc)
        return {
            "index": q_num,
            "total": q_total,
            "skill_name": skill_name,
            "difficulty": difficulty,
            "is_pco": is_pco,
            "question": f"Explain the key concept of {skill_name} and provide an example.",
            "hint": f"Think about the core principles of {skill_name}.",
            "correct_answer": f"A thorough understanding of {skill_name} with practical examples.",
            "explanation": f"{skill_name} involves understanding its fundamentals and applications.",
        }


def _evaluate_answer(question: str, correct_answer: str, student_answer: str, thinking_mode: str) -> dict:
    feedback_style = (
        "FAST mode: Keep feedback concise and actionable."
        if thinking_mode == "fast"
        else "DEEP mode: Give layered feedback about reasoning quality, conceptual gaps, and next-step improvement."
    )
    prompt = (
        "You are an AI tutor evaluating a student's answer.\n"
        f"Question: {question}\n"
        f"Correct answer: {correct_answer}\n"
        f"Student's answer: {student_answer}\n"
        f"{feedback_style}\n"
        "Respond with JSON ONLY:\n"
        '{"correct":true/false,"message":"1-2 sentence feedback",'
        '"explanation":"detailed explanation","suggested_mastery_delta":0.05}'
    )
    try:
        data = _parse_json(_call_llm(prompt, max_tokens=300, temperature=0.3))
        return {
            "correct": bool(data.get("correct", False)),
            "message": data.get("message") or "Your answer was evaluated.",
            "explanation": data.get("explanation") or "",
            "correct_answer": correct_answer,
            "skill_name": "",
            "suggested_mastery_delta": float(data.get("suggested_mastery_delta", 0)),
        }
    except Exception as exc:
        logger.warning("Answer eval failed: %s", exc)
        correct = student_answer.lower() in correct_answer.lower()
        return {
            "correct": correct,
            "message": "Good effort!" if correct else "Not quite right.",
            "explanation": correct_answer,
            "correct_answer": correct_answer,
            "skill_name": "",
            "suggested_mastery_delta": 0.05 if correct else -0.03,
        }


def _generate_hint(question: str, hint_num: int) -> tuple[str, bool]:
    is_final = hint_num >= 3
    suffix = "Be more direct now." if is_final else "Don't give away the answer."
    prompt = f'Question: "{question}"\nGenerate hint #{hint_num} of 3. {suffix}\nReply with just the hint.'
    try:
        return (_call_llm(prompt, max_tokens=150, temperature=0.5).strip() or "Think about the core concept."), is_final
    except Exception:
        return "Consider the key principles involved.", is_final


def _explain_concept(skill_name: str, question: str) -> str:
    prompt = (
        f'A student asked for an explanation while working on "{skill_name}".\n'
        f'Question: "{question}"\n'
        "Give a clear, concise explanation (2–3 paragraphs)."
    )
    try:
        return _call_llm(prompt, max_tokens=400, temperature=0.5).strip()
    except Exception:
        return f"The concept of {skill_name} involves understanding its core principles and applications."


def _stream_llm(messages: list[dict]):
    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=settings.llm_api_key or "no-key",
            base_url=settings.llm_base_url,
        )
        stream = client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            temperature=0.7,
            max_tokens=600,
            stream=True,
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield f"data: {json.dumps({'token': chunk.choices[0].delta.content})}\n\n"
    except Exception as exc:
        yield f"data: {json.dumps({'error': str(exc)})}\n\n"


# ── Skill queue ───────────────────────────────────────────────────────────────


def _build_skill_queue(
    user_id: int,
    course_id: int,
    driver: Neo4jDriver,
    max_q: int,
    filter_skill_idx: int | None = None,
    selected_skill_names: list[str] | None = None,
) -> tuple[list[str], list[float], set[str]]:
    from app.modules.cognitive_diagnosis.repository import CognitiveDiagnosisRepository
    from app.modules.cognitive_diagnosis.service import CognitiveDiagnosisService

    db = settings.neo4j_database
    with driver.session(database=db) as neo_session:
        repo = CognitiveDiagnosisRepository(neo_session)
        skill_rows = repo.get_student_selected_skills(user_id, course_id)
        course_rows = repo.get_all_skills_with_concepts(course_id)
        mastery_rows = repo.get_student_mastery(user_id, course_id)

    if not skill_rows and not course_rows:
        return [], [], set()

    all_names = [r["skill_name"] for r in skill_rows if r["skill_name"]]
    all_course_names = [r["skill_name"] for r in course_rows if r["skill_name"]]
    mastery_map = {r["skill_name"]: float(r.get("mastery", 0.3)) for r in mastery_rows}
    all_mastery = [mastery_map.get(n, 0.3) for n in all_names]

    pco_names: set[str] = set()
    try:
        svc = CognitiveDiagnosisService(driver)
        review = svc.review_session(user_id, course_id, top_k=5)
        pco_names = {p.skill_name for p in review.pco_skills}
    except Exception:
        pass

    if filter_skill_idx is not None and 0 <= filter_skill_idx < len(all_names):
        sn = all_names[filter_skill_idx]
        m = all_mastery[filter_skill_idx]
        return [sn] * max_q, [m] * max_q, pco_names

    if selected_skill_names:
        normalized = [s.strip() for s in selected_skill_names if s and s.strip()]
        # Validate against the student's own enrolled skills, not all course skills
        valid_set = set(all_names)
        chosen = [s for s in normalized if s in valid_set]
        if chosen:
            # Honor max_q even if student selected fewer unique skills
            # by cycling through the chosen set.
            expanded: list[str] = []
            idx = 0
            while len(expanded) < max_q:
                expanded.append(chosen[idx % len(chosen)])
                idx += 1
            chosen_mastery = [mastery_map.get(n, 0.3) for n in expanded]
            return expanded, chosen_mastery, pco_names

    indexed = sorted(
        zip(all_names, all_mastery, strict=False),
        key=lambda x: (-(x[0] in pco_names), -(1.0 - x[1])),
    )
    top = indexed[:max_q]
    names = [t[0] for t in top]
    mastery_vals = [t[1] for t in top]
    if not names:
        fallback = all_course_names[:max_q]
        return fallback, [mastery_map.get(n, 0.3) for n in fallback], pco_names
    return names, mastery_vals, pco_names


# ── Summary ───────────────────────────────────────────────────────────────────


def _summary(sess: ReviewSession) -> dict:
    correct = sum(1 for r in sess.results if r["is_correct"])
    total = len(sess.results)
    pct = (correct / max(total, 1)) * 100
    score = correct * 10

    skill_map: dict[str, dict] = {}
    for r in sess.results:
        sn = r["skill_name"]
        if sn not in skill_map:
            skill_map[sn] = {
                "skill_name": sn, "total": 0, "correct": 0,
                "mastery_start": r["mastery_before"], "mastery_end": r["mastery_after"],
                "is_pco": r["is_pco"],
            }
        skill_map[sn]["total"] += 1
        if r["is_correct"]:
            skill_map[sn]["correct"] += 1
        skill_map[sn]["mastery_end"] = r["mastery_after"]

    strengths = [s for s, v in skill_map.items() if v["correct"] == v["total"] > 0]
    weak = [s for s, v in skill_map.items() if v["correct"] < v["total"] / 2]
    advice = "Excellent!" if pct >= 80 else ("Keep practicing!" if pct >= 50 else "Consider revisiting these skills.")

    return {
        "score": score,
        "max_score": total * 10,
        "correct_count": correct,
        "total_questions": total,
        "percentage": round(pct, 1),
        "results": sess.results,
        "skills_summary": list(skill_map.values()),
        "strengths": strengths,
        "areas_for_improvement": weak,
        "llm_feedback": f"You answered {correct}/{total} questions correctly ({pct:.0f}%). {advice}",
        "needs_replan": pct < 60,
    }


def _mastery_portfolio_insight(skill_names: list[str], mastery: list[float]) -> dict:
    pairs: dict[str, float] = {}
    for name, m in zip(skill_names, mastery, strict=False):
        if name and name not in pairs:
            pairs[name] = float(m)
    if not pairs:
        return {"avg": 0.0, "strengths": [], "weaknesses": [], "text": "No mastery signals available yet."}

    ordered = sorted(pairs.items(), key=lambda x: x[1], reverse=True)
    avg = sum(pairs.values()) / max(len(pairs), 1)
    strengths = [name for name, _ in ordered[:2]]
    weaknesses = [name for name, _ in list(reversed(ordered))[:2]]
    text = (
        f"Current mastery snapshot: average {avg:.0%}. "
        f"Strengths: {', '.join(strengths) if strengths else 'N/A'}. "
        f"Focus areas: {', '.join(weaknesses) if weaknesses else 'N/A'}."
    )
    return {"avg": avg, "strengths": strengths, "weaknesses": weaknesses, "text": text}


# ── Dependency types ──────────────────────────────────────────────────────────

StudentDep = Annotated[User, Depends(require_role(UserRole.STUDENT))]
Neo4jDep = Annotated[Neo4jDriver | None, Depends(get_neo4j_driver)]


def _require_neo4j(driver: Neo4jDep) -> Neo4jDriver:
    if driver is None:
        raise HTTPException(status_code=503, detail="Neo4j is not available")
    return driver


# ── Next-question helper ──────────────────────────────────────────────────────


def _advance_question(sess: ReviewSession, q_idx: int) -> dict | None:
    if q_idx >= len(sess.skill_names):
        return None
    q = _generate_question(
        sess.skill_names[q_idx],
        sess.mastery[q_idx],
        sess.skill_names[q_idx] in sess.pco_skill_names,
        q_idx + 1,
        len(sess.skill_names),
        sess.thinking_mode,
    )
    sess.current_question = q
    sess.hint_count = 0
    return q


def _record_result(
    sess: ReviewSession,
    answer_text: str,
    mastery_delta: float,
    is_correct: bool,
    points: int,
    feedback_snippet: str = "",
) -> None:
    q = sess.current_question
    if q is None:
        return
    q_idx = len(sess.results)
    m_before = sess.mastery[q_idx] if q_idx < len(sess.mastery) else 0.0
    m_after = max(0.0, min(1.0, m_before + mastery_delta))
    sess.results.append({
        "index": q["index"],
        "skill_name": q["skill_name"],
        "question": q["question"],
        "correct_answer": q["correct_answer"],
        "student_answer": answer_text,
        "is_correct": is_correct,
        "mastery_delta": mastery_delta,
        "mastery_before": m_before,
        "mastery_after": m_after,
        "difficulty": q["difficulty"],
        "is_pco": q["is_pco"],
        "points": points,
        "feedback_snippet": feedback_snippet[:80],
    })
    sess.progress["current"] += 1
    if is_correct:
        sess.progress["correct"] += 1
        sess.progress["score"] += 10


def _finish_or_next(sess: ReviewSession) -> tuple[bool, dict | None, str | None, dict | None]:
    """Returns (is_complete, next_q, completion_message, review_summary)."""
    next_idx = len(sess.results)
    if next_idx >= len(sess.skill_names):
        sess.is_complete = True
        sess.current_question = None
        pct = (sess.progress["correct"] / max(sess.progress["total"], 1)) * 100
        msg = (
            f"🎉 Review complete! You got {sess.progress['correct']}/{sess.progress['total']} "
            f"correct ({pct:.0f}%). Well done!"
        )
        return True, None, msg, _summary(sess)
    next_q = _advance_question(sess, next_idx)
    return False, next_q, None, None


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/health")
def api_health() -> dict:
    return {"status": "ok", "service": "review-chat"}


@router.post("/review/start")
def review_start(body: dict, student: StudentDep, driver: Neo4jDep) -> dict:
    _cleanup_sessions()
    dataset_id = str(body.get("dataset_id", ""))
    thinking_mode = str(body.get("thinking_mode", "fast")).strip().lower()
    if thinking_mode not in {"fast", "deep"}:
        thinking_mode = "fast"
    default_q = 5 if thinking_mode == "fast" else 9
    max_questions = max(1, min(int(body.get("max_questions", default_q)), 20))
    course_id = _parse_course_id(dataset_id)
    neo = _require_neo4j(driver)

    selected_skills = body.get("selected_skills")
    selected_skill_names = selected_skills if isinstance(selected_skills, list) else None
    skill_names, mastery, pco_names = _build_skill_queue(
        student.id, course_id, neo, max_questions, selected_skill_names=selected_skill_names
    )
    if not skill_names:
        raise HTTPException(status_code=404, detail="No skills found for this student/course")

    session_id = str(uuid.uuid4())
    progress = {"current": 0, "total": len(skill_names), "correct": 0, "score": 0, "max_score": len(skill_names) * 10}
    sess = ReviewSession(
        session_id=session_id, user_id=student.id, course_id=course_id,
        skill_names=skill_names, mastery=list(mastery), pco_skill_names=pco_names,
        results=[], current_question=None, progress=progress, created_at=time.time(),
        thinking_mode=thinking_mode, chat_history=[],
    )
    _sessions[session_id] = sess
    q = _advance_question(sess, 0)
    insight = _mastery_portfolio_insight(skill_names, mastery)
    return {
        "session_id": session_id,
        "greeting": (
            f"👋 Welcome back! I'm your Review Fellow. {('Fast Review' if thinking_mode == 'fast' else 'Deep Review')} "
            f"mode is on, and we have {len(skill_names)} question(s). "
            f"{insight['text']} "
            f"{'We will move quickly with concise checks.' if thinking_mode == 'fast' else 'We will focus on reasoning and deeper understanding.'}"
        ),
        "progress": progress,
        "current_question": q,
        "thinking_mode": thinking_mode,
        "portfolio_insight": insight,
    }


@router.post("/review/options")
def review_options(body: dict, student: StudentDep, driver: Neo4jDep) -> dict:
    dataset_id = str(body.get("dataset_id", ""))
    course_id = _parse_course_id(dataset_id)
    neo = _require_neo4j(driver)
    db = settings.neo4j_database
    from app.modules.cognitive_diagnosis.repository import CognitiveDiagnosisRepository
    from app.modules.cognitive_diagnosis.service import CognitiveDiagnosisService

    with neo.session(database=db) as neo_session:
        repo = CognitiveDiagnosisRepository(neo_session)
        selected_rows = repo.get_student_selected_skills(student.id, course_id)
        course_rows = repo.get_all_skills_with_concepts(course_id)
        mastery_rows = repo.get_student_mastery(student.id, course_id)

    selected_names = [r["skill_name"] for r in selected_rows if r.get("skill_name")]
    all_course_names = [r["skill_name"] for r in course_rows if r.get("skill_name")]
    mastery_map = {r["skill_name"]: float(r.get("mastery", 0.3)) for r in mastery_rows}

    suggestions: list[str] = []
    try:
        svc = CognitiveDiagnosisService(neo)
        review = svc.review_session(student.id, course_id, top_k=6)
        # Only keep suggestions that are in the student's enrolled skill set
        enrolled_set = set(selected_names)
        suggestions = [s.skill_name for s in review.pco_skills if s.skill_name and s.skill_name in enrolled_set]
    except Exception:
        suggestions = []

    if not suggestions:
        weakest_first = sorted(selected_names, key=lambda n: mastery_map.get(n, 0.3))
        suggestions = weakest_first[:6]

    return {
        "suggested_skills": suggestions,
        "selected_skills": selected_names,
        "all_skills": all_course_names,
        "mastery_map": mastery_map,
        "question_count_bounds": {"min": 1, "max": 20, "default_fast": 5, "default_deep": 9},
    }


@router.get("/review/session/{session_id}")
def check_session(session_id: str, student: StudentDep) -> dict:
    sess = _sessions.get(session_id)
    if sess is None or sess.user_id != student.id:
        return {"alive": False, "is_complete": True}
    return {"alive": (time.time() - sess.created_at) < SESSION_TTL, "is_complete": sess.is_complete}


@router.post("/review/next-question")
def next_question(body: dict, student: StudentDep) -> dict:
    sess = _get_session(str(body.get("session_id", "")), student.id)
    q_idx = len(sess.results)
    if q_idx >= len(sess.skill_names):
        sess.is_complete = True
        return {"current_question": None, "progress": sess.progress}
    q = _advance_question(sess, q_idx)
    return {"current_question": q, "progress": sess.progress}


@router.post("/review/answer")
def answer_question(body: dict, student: StudentDep) -> dict:
    sess = _get_session(str(body.get("session_id", "")), student.id)
    if sess.current_question is None:
        raise HTTPException(status_code=400, detail="No active question")

    answer_text = str(body.get("answer", ""))
    q = sess.current_question
    feedback = _evaluate_answer(q["question"], q["correct_answer"], answer_text, sess.thinking_mode)
    feedback["skill_name"] = q["skill_name"]

    _record_result(
        sess, answer_text, feedback.get("suggested_mastery_delta", 0.0),
        feedback["correct"], 10 if feedback["correct"] else 0, feedback.get("message", ""),
    )
    is_complete, next_q, msg, rev_summary = _finish_or_next(sess)
    return {"progress": sess.progress, "feedback": feedback, "is_complete": is_complete,
            "next_question": next_q, "completion_message": msg, "review_summary": rev_summary}


@router.post("/review/skip")
def skip_question(body: dict, student: StudentDep) -> dict:
    sess = _get_session(str(body.get("session_id", "")), student.id)
    if sess.current_question is None:
        raise HTTPException(status_code=400, detail="No active question")

    q = sess.current_question
    feedback = {
        "correct": False,
        "message": "Question skipped. Keep going!",
        "explanation": f"The answer was: {q['correct_answer']}",
        "correct_answer": q["correct_answer"],
        "skill_name": q["skill_name"],
        "suggested_mastery_delta": 0.0,
    }
    _record_result(sess, "[skipped]", 0.0, False, 0, "Skipped")
    is_complete, next_q, msg, rev_summary = _finish_or_next(sess)
    return {"progress": sess.progress, "feedback": feedback, "is_complete": is_complete,
            "next_question": next_q, "completion_message": msg, "review_summary": rev_summary}


@router.post("/review/hint")
def get_hint(body: dict, student: StudentDep) -> dict:
    sess = _get_session(str(body.get("session_id", "")), student.id)
    if sess.current_question is None:
        raise HTTPException(status_code=400, detail="No active question")
    sess.hint_count += 1
    hint, is_final = _generate_hint(sess.current_question["question"], sess.hint_count)
    return {"hint": hint, "is_final_hint": is_final}


@router.post("/review/explain")
def explain_concept(body: dict, student: StudentDep) -> dict:
    sess = _get_session(str(body.get("session_id", "")), student.id)
    if sess.current_question is None:
        raise HTTPException(status_code=400, detail="No active question")
    explanation = _explain_concept(sess.current_question["skill_name"], sess.current_question["question"])
    return {"explanation": explanation}


@router.post("/review/chat/stream")
def review_chat_stream(body: dict, student: StudentDep) -> StreamingResponse:
    sess = _get_session(str(body.get("session_id", "")), student.id)
    message = str(body.get("message", ""))
    q = sess.current_question
    req_mode = str(body.get("thinking_mode", sess.thinking_mode)).strip().lower()
    mode = req_mode if req_mode in {"fast", "deep"} else sess.thinking_mode
    style = (
        "FAST mode: concise, practical, high-clarity responses in short paragraphs."
        if mode == "fast"
        else "DEEP mode: conversational but rigorous. Explain reasoning step-by-step, and ask one reflective follow-up when useful."
    )
    profile = _mastery_portfolio_insight(sess.skill_names, sess.mastery)
    strengths = ", ".join(profile["strengths"]) if profile["strengths"] else "N/A"
    weaknesses = ", ".join(profile["weaknesses"]) if profile["weaknesses"] else "N/A"
    system = (
        "You are an elite learning coach inside a study app. "
        "Be warm, natural, and adaptive. "
        f"{style} "
        f"Student mastery profile: avg={profile['avg']:.0%}, strengths={strengths}, weaknesses={weaknesses}. "
        "Prioritize helping with weaknesses while reinforcing strengths."
        f"The student is reviewing '{q['skill_name'] if q else 'a topic'}'."
        + (f" Current question: {q['question']}" if q else "")
    )
    history = sess.chat_history or []
    recent = history[-8:]
    messages = [{"role": "system", "content": system}, *recent, {"role": "user", "content": message}]
    sess.chat_history = [*recent, {"role": "user", "content": message}]
    return StreamingResponse(
        _stream_llm(messages),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/review/practice-skill")
def practice_skill(body: dict, student: StudentDep, driver: Neo4jDep) -> dict:
    _cleanup_sessions()
    dataset_id = str(body.get("dataset_id", ""))
    skill_idx = int(body.get("skill_id", 0))
    thinking_mode = str(body.get("thinking_mode", "fast")).strip().lower()
    if thinking_mode not in {"fast", "deep"}:
        thinking_mode = "fast"
    default_n = 3 if thinking_mode == "fast" else 5
    n_q = max(1, min(int(body.get("n_questions", default_n)), 10))
    course_id = _parse_course_id(dataset_id)
    neo = _require_neo4j(driver)

    skill_names, mastery, pco_names = _build_skill_queue(student.id, course_id, neo, n_q, filter_skill_idx=skill_idx)
    if not skill_names:
        raise HTTPException(status_code=404, detail="Skill not found")

    session_id = str(uuid.uuid4())
    progress = {"current": 0, "total": n_q, "correct": 0, "score": 0, "max_score": n_q * 10}
    sess = ReviewSession(
        session_id=session_id, user_id=student.id, course_id=course_id,
        skill_names=skill_names, mastery=list(mastery), pco_skill_names=pco_names,
        results=[], current_question=None, progress=progress, created_at=time.time(),
        thinking_mode=thinking_mode, chat_history=[],
    )
    _sessions[session_id] = sess
    q = _advance_question(sess, 0)
    return {
        "session_id": session_id,
        "greeting": (
            f"Let's practice **{skill_names[0]}** in {('Fast' if thinking_mode == 'fast' else 'Deep')} mode! "
            f"I'll ask {n_q} question(s)."
        ),
        "progress": progress,
        "current_question": q,
        "thinking_mode": thinking_mode,
    }


@router.post("/chat/stream")
def general_chat_stream(body: dict, student: StudentDep) -> StreamingResponse:
    message = str(body.get("message", ""))
    dataset_id = str(body.get("dataset_id", ""))
    session_id = str(body.get("session_id", "")) or str(uuid.uuid4())

    thinking_mode = str(body.get("thinking_mode", "fast")).strip().lower()
    if thinking_mode not in {"fast", "deep"}:
        thinking_mode = "fast"
    tone = (
        "Keep responses concise, practical, and easy to scan."
        if thinking_mode == "fast"
        else "Use a richer tutoring style with clear structure, examples, and reasoning."
    )
    system = (
        "You are a high-quality AI tutor for a learning management system. "
        "Your style should feel natural, supportive, and conversational. "
        f"{tone}"
    )
    with contextlib.suppress(Exception):
        system += f" Student is working on course {_parse_course_id(dataset_id)}."

    if session_id in _sessions:
        top3 = ", ".join(_sessions[session_id].skill_names[:3])
        system += f" Reviewing: {top3}."

    def _with_sid():
        yield f"data: {json.dumps({'session_id': session_id})}\n\n"
        yield from _stream_llm([{"role": "system", "content": system}, {"role": "user", "content": message}])

    return StreamingResponse(
        _with_sid(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/review/analysis")
def review_analysis(body: dict, student: StudentDep) -> dict:
    dataset_id = str(body.get("dataset_id", ""))
    session_summary = body.get("session_summary") or {}
    if not isinstance(session_summary, dict):
        session_summary = {}

    correct = int(session_summary.get("correct", 0) or 0)
    total = int(session_summary.get("total", 0) or 0)
    score = int(session_summary.get("score", 0) or 0)
    skills = session_summary.get("skills") or []
    if not isinstance(skills, list):
        skills = []
    skills_text = ", ".join([str(s) for s in skills[:8]]) or "N/A"

    prompt = (
        "You are an empathetic academic coach. "
        "Write constructive feedback for a student after a review session.\n"
        f"Student id: {student.id}\n"
        f"Dataset: {dataset_id}\n"
        f"Correct/Total: {correct}/{total}\n"
        f"Score: {score}\n"
        f"Skills reviewed: {skills_text}\n"
        "Output in markdown with these exact sections:\n"
        "## What You Did Well\n"
        "## Where You Struggled\n"
        "## How To Fix It (Next Session)\n"
        "## One Small Action Now\n"
        "Be specific and practical, avoid generic phrases."
    )
    text = _call_llm(prompt, max_tokens=500, temperature=0.5)
    return {"analysis": text.strip() or "No analysis available yet. Complete one session first."}
