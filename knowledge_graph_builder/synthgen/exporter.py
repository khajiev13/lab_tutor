"""synthgen.exporter — write synthetic data to Postgres, Neo4j and Parquet.

Writes:
  Postgres:
    - users (role='student', email pattern synth_*@labtutor.local)
  Neo4j:
    - USER:STUDENT:SYNTHETIC nodes + SYNTHETIC_RUN label
    - ENROLLED_IN_CLASS edges (each student → all Roma's classes)
    - ANSWERED edges (student → QUESTION, all tagged synthetic)
    - MASTERED edges (IRT ground truth)
  Parquet:
    - data/synthgen/<run_id>/train.parquet
    - data/synthgen/<run_id>/test.parquet
    - data/synthgen/<run_id>/vocab.json
    - data/synthgen/<run_id>/mastery_ground_truth.parquet
"""
from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from .config import SynthGenConfig

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Postgres: create user rows
# ─────────────────────────────────────────────────────────────────────────────

def _psycopg3_url(url: str) -> str:
    """Ensure the URL uses psycopg (v3) dialect."""
    return url.replace("postgresql://", "postgresql+psycopg://", 1).replace(
        "postgres://", "postgresql+psycopg://", 1
    ) if "+psycopg" not in url else url


def write_students_to_postgres(
    students: list[dict],
    cfg: SynthGenConfig,
) -> dict[str, int]:
    """Insert synthetic students into Postgres `users` table.

    Returns mapping {student_id -> postgres_user_id}.
    Skips any student whose email already exists (idempotent).
    Uses bulk-upsert + single SELECT to avoid N round-trips.
    """
    engine = create_engine(_psycopg3_url(cfg.postgres_url))

    emails = [s["email"] for s in students]
    email_to_synth_id = {s["email"]: s["student_id"] for s in students}

    id_map: dict[str, int] = {}

    with engine.begin() as conn:
        # 1. Bulk-insert new students (skip conflicts) via executemany
        conn.execute(
            text(
                """
                INSERT INTO users
                    (email, first_name, last_name, role,
                     hashed_password, is_active, is_superuser, is_verified, created_at)
                VALUES
                    (:email, :first_name, :last_name, 'STUDENT'::user_role,
                     'SYNTHETIC_NO_PASSWORD', true, false, false, :now)
                ON CONFLICT (email) DO NOTHING
                """
            ),
            [
                {
                    "email": s["email"],
                    "first_name": s["first_name"],
                    "last_name": s["last_name"],
                    "now": datetime.now(UTC),
                }
                for s in students
            ],
        )

        # 2. Single bulk SELECT to get all IDs
        rows = conn.execute(
            text("SELECT id, email FROM users WHERE email = ANY(:emails)"),
            {"emails": emails},
        ).fetchall()

        for row in rows:
            pg_id, email = row[0], row[1]
            synth_id = email_to_synth_id.get(email)
            if synth_id:
                id_map[synth_id] = pg_id

    logger.info(
        "Postgres: upserted %d synthetic students", len(id_map)
    )
    return id_map


# ─────────────────────────────────────────────────────────────────────────────
# Neo4j: write USER nodes
# ─────────────────────────────────────────────────────────────────────────────

def write_student_nodes_to_neo4j(
    students: list[dict],
    pg_id_map: dict[str, int],
    neo4j_session,
    cfg: SynthGenConfig,
) -> None:
    """Upsert USER:STUDENT:SYNTHETIC nodes in Neo4j."""
    batch_size = cfg.batch_size

    def _write(tx, batch):
        tx.run(
            """
            UNWIND $rows AS s
            MERGE (u:USER:STUDENT {id: s.pg_id})
            SET u:SYNTHETIC,
                u:SYNTHETIC_RUN,
                u.email       = s.email,
                u.first_name  = s.first_name,
                u.last_name   = s.last_name,
                u.synthetic   = true,
                u.run_id      = s.run_id
            """,
            rows=batch,
        )

    rows = [
        {
            "pg_id": pg_id_map[s["student_id"]],
            "email": s["email"],
            "first_name": s["first_name"],
            "last_name": s["last_name"],
            "run_id": cfg.run_id,
        }
        for s in students
    ]
    for start in range(0, len(rows), batch_size):
        neo4j_session.execute_write(_write, rows[start : start + batch_size])
    logger.info("Neo4j: wrote %d student nodes", len(rows))


# ─────────────────────────────────────────────────────────────────────────────
# Neo4j: enroll students in Roma's classes
# ─────────────────────────────────────────────────────────────────────────────

def enroll_students_in_classes(
    pg_id_map: dict[str, int],
    class_ids: list[int],
    neo4j_session,
    cfg: SynthGenConfig,
) -> None:
    """Create ENROLLED_IN_CLASS edges for every synthetic student."""
    batch_size = cfg.batch_size
    all_pg_ids = list(pg_id_map.values())

    for class_id in class_ids:
        for start in range(0, len(all_pg_ids), batch_size):
            chunk = all_pg_ids[start : start + batch_size]

            def _write(tx, ids=chunk, cid=class_id):
                tx.run(
                    """
                    UNWIND $ids AS sid
                    MATCH (u:USER {id: sid})
                    MATCH (c:CLASS {id: $cid})
                    MERGE (u)-[:ENROLLED_IN_CLASS]->(c)
                    """,
                    ids=ids,
                    cid=cid,
                )

            neo4j_session.execute_write(_write)

    logger.info(
        "Enrolled %d students in %d classes", len(all_pg_ids), len(class_ids)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Neo4j: write ANSWERED edges
# ─────────────────────────────────────────────────────────────────────────────

def write_answered_edges(
    interactions_df: pd.DataFrame,
    pg_id_map: dict[str, int],
    neo4j_session,
    cfg: SynthGenConfig,
) -> None:
    """Write ANSWERED relationship edges in batches."""
    batch_size = cfg.batch_size

    def _write(tx, batch):
        tx.run(
            """
            UNWIND $rows AS row
            MATCH (u:USER:STUDENT {id: row.pg_id})
            MATCH (q:QUESTION {id: row.question_id})
            CREATE (u)-[r:ANSWERED {
                answered_right  : row.correct,
                answered_at     : datetime(row.answered_at),
                synthetic       : true,
                run_id          : row.run_id
            }]->(q)
            """,
            rows=batch,
        )

    rows_all = []
    for _, row in interactions_df.iterrows():
        pg_id = pg_id_map.get(row["student_id"])
        if pg_id is None:
            continue
        ts = int(row["timestamp_sec"])
        dt_iso = datetime.utcfromtimestamp(ts).isoformat() + "Z"
        rows_all.append(
            {
                "pg_id": pg_id,
                "question_id": row["question_id"],
                "correct": bool(row["correct"]),
                "answered_at": dt_iso,
                "run_id": cfg.run_id,
            }
        )

    total = len(rows_all)
    for start in range(0, total, batch_size):
        batch = rows_all[start : start + batch_size]
        neo4j_session.execute_write(_write, batch)
        if (start // batch_size) % 20 == 0:
            logger.info("ANSWERED edges: %d/%d", min(start + batch_size, total), total)

    logger.info("Wrote %d ANSWERED edges to Neo4j", total)


# ─────────────────────────────────────────────────────────────────────────────
# Neo4j: write MASTERED edges
# ─────────────────────────────────────────────────────────────────────────────

def write_mastery_to_neo4j(
    mastery_df: pd.DataFrame,
    pg_id_map: dict[str, int],
    neo4j_session,
    cfg: SynthGenConfig,
) -> None:
    """Write MASTERED edges for all (student, skill) pairs."""
    batch_size = cfg.batch_size
    now_ts = int(time.time())

    def _write(tx, batch):
        tx.run(
            """
            UNWIND $rows AS row
            MATCH (u:USER:STUDENT {id: row.pg_id})
            MATCH (s {name: row.skill_id})
            WHERE (s:SKILL OR s:BOOK_SKILL OR s:MARKET_SKILL)
            MERGE (u)-[r:MASTERED]->(s)
            SET r.mastery          = row.mastery,
                r.decay            = row.decay,
                r.status           = row.status,
                r.attempt_count    = row.attempt_count,
                r.correct_count    = row.correct_count,
                r.updated_at_ts    = row.updated_at_ts,
                r.model_version    = row.model_version,
                r.last_practice_ts = row.last_practice_ts,
                r.synthetic        = true,
                r.run_id           = row.run_id
            """,
            rows=batch,
        )

    rows_all = []
    for _, row in mastery_df.iterrows():
        pg_id = pg_id_map.get(row["student_id"])
        if pg_id is None:
            continue
        rows_all.append(
            {
                "pg_id": pg_id,
                "skill_id": row["skill_id"],
                "mastery": float(row["mastery"]),
                "decay": float(row["decay"]),
                "status": str(row["status"]),
                "attempt_count": int(row["attempt_count"]),
                "correct_count": int(row["correct_count"]),
                "updated_at_ts": now_ts,
                "model_version": f"irt_gt_{cfg.run_id}",
                "last_practice_ts": row.get("last_practice_ts"),
                "run_id": cfg.run_id,
            }
        )

    total = len(rows_all)
    for start in range(0, total, batch_size):
        batch = rows_all[start : start + batch_size]
        neo4j_session.execute_write(_write, batch)
        if (start // batch_size) % 10 == 0:
            logger.info("MASTERED edges: %d/%d", min(start + batch_size, total), total)

    logger.info("Wrote %d MASTERED edges to Neo4j", total)


# ─────────────────────────────────────────────────────────────────────────────
# Neo4j: write SELECTED_SKILL edges (required by teacher dashboard queries)
# ─────────────────────────────────────────────────────────────────────────────

def write_selected_skill_edges(
    mastery_df: pd.DataFrame,
    pg_id_map: dict[str, int],
    neo4j_session,
    cfg: SynthGenConfig,
    student_skills_map: dict[str, set[str]] | None = None,
) -> None:
    """Create SELECTED_SKILL edges for synthetic students.

    When ``student_skills_map`` is provided (mapping ``student_id`` →
    ``{skill_name, …}``), only the skills explicitly selected for each student
    are written.  This reflects the per-student subset chosen by the simulator
    and prevents spurious SELECTED_SKILL edges for skills the student never
    practised.

    Without the map (backwards-compat) every skill in ``mastery_df`` is used,
    which mirrors the old all-skills behaviour.
    """
    batch_size = cfg.batch_size
    now_iso = datetime.now(UTC).isoformat()

    seen: set[tuple[int, str]] = set()
    rows_all: list[dict] = []
    for _, row in mastery_df.iterrows():
        sid = str(row["student_id"])
        skill_name = str(row["skill_id"])

        # Skip skills not in this student's selected set (when map is provided)
        if student_skills_map is not None:
            if skill_name not in student_skills_map.get(sid, set()):
                continue

        pg_id = pg_id_map.get(row["student_id"])
        if pg_id is None:
            continue
        key = (pg_id, skill_name)
        if key in seen:
            continue
        seen.add(key)
        rows_all.append({"pg_id": pg_id, "skill_name": skill_name})

    def _write(tx, batch):
        tx.run(
            """
            UNWIND $rows AS row
            MATCH (u:USER:STUDENT {id: row.pg_id})
            MATCH (s {name: row.skill_name})
            WHERE (s:SKILL OR s:BOOK_SKILL OR s:MARKET_SKILL)
            MERGE (u)-[r:SELECTED_SKILL]->(s)
            ON CREATE SET r.selected_at = datetime($now), r.source = 'synthetic'
            ON MATCH  SET r.source = 'synthetic'
            """,
            rows=batch,
            now=now_iso,
        )

    total = len(rows_all)
    for start in range(0, total, batch_size):
        batch = rows_all[start : start + batch_size]
        neo4j_session.execute_write(_write, batch)
        if (start // batch_size) % 10 == 0:
            logger.info(
                "SELECTED_SKILL edges: %d/%d", min(start + batch_size, total), total
            )

    logger.info("Wrote %d SELECTED_SKILL edges to Neo4j", total)


# ─────────────────────────────────────────────────────────────────────────────
# Neo4j: write OPENED_VIDEO / OPENED_READING edges
# ─────────────────────────────────────────────────────────────────────────────

def write_resource_edges(
    resource_df: pd.DataFrame,
    pg_id_map: dict[str, int],
    neo4j_session,
    cfg: SynthGenConfig,
) -> None:
    """Write OPENED_VIDEO and OPENED_READING edges for synthetic students.

    ``resource_df`` must have columns:
        student_id    – synthetic UUID
        resource_id   – video_id or reading_id
        resource_type – 'video' or 'reading'
        opened_at_sec – list of Unix timestamps (ints)

    Each (student, resource) pair becomes one relationship whose ``opened_at``
    property holds a list of Neo4j datetime values, one per open event.
    Using MERGE + SET makes the write idempotent for re-runs.
    """
    if resource_df is None or resource_df.empty:
        logger.info("No resource interactions to write.")
        return

    batch_size = cfg.batch_size

    def _to_iso(ts_sec: int) -> str:
        return datetime.fromtimestamp(ts_sec, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _write_video(tx, batch):
        tx.run(
            """
            UNWIND $rows AS row
            MATCH (u:USER:STUDENT {id: row.pg_id})
            MATCH (v:VIDEO_RESOURCE {id: row.resource_id})
            MERGE (u)-[e:OPENED_VIDEO]->(v)
            SET e.opened_at = [ts IN row.opened_at | datetime(ts)],
                e.synthetic  = true,
                e.run_id     = row.run_id
            """,
            rows=batch,
        )

    def _write_reading(tx, batch):
        tx.run(
            """
            UNWIND $rows AS row
            MATCH (u:USER:STUDENT {id: row.pg_id})
            MATCH (r:READING_RESOURCE {id: row.resource_id})
            MERGE (u)-[e:OPENED_READING]->(r)
            SET e.opened_at = [ts IN row.opened_at | datetime(ts)],
                e.synthetic  = true,
                e.run_id     = row.run_id
            """,
            rows=batch,
        )

    video_rows: list[dict] = []
    reading_rows: list[dict] = []

    for _, row in resource_df.iterrows():
        pg_id = pg_id_map.get(row["student_id"])
        if pg_id is None:
            continue
        ts_list = row["opened_at_sec"]
        if not ts_list:
            continue
        record = {
            "pg_id": pg_id,
            "resource_id": row["resource_id"],
            "opened_at": [_to_iso(int(t)) for t in ts_list],
            "run_id": cfg.run_id,
        }
        if row["resource_type"] == "video":
            video_rows.append(record)
        else:
            reading_rows.append(record)

    for label, rows_all, writer in [
        ("OPENED_VIDEO", video_rows, _write_video),
        ("OPENED_READING", reading_rows, _write_reading),
    ]:
        total = len(rows_all)
        for start in range(0, total, batch_size):
            batch = rows_all[start : start + batch_size]
            neo4j_session.execute_write(writer, batch)
            if (start // batch_size) % 10 == 0:
                logger.info("%s edges: %d/%d", label, min(start + batch_size, total), total)
        logger.info("Wrote %d %s edges to Neo4j", total, label)


# ─────────────────────────────────────────────────────────────────────────────
# Parquet / JSON output
# ─────────────────────────────────────────────────────────────────────────────

def save_parquet_artifacts(
    interactions_df: pd.DataFrame,
    mastery_df: pd.DataFrame,
    students: list[dict],
    questions: list[dict],
    skills: list[dict],
    pg_id_map: dict[str, int],
    cfg: SynthGenConfig,
    prereq_edges: list[dict] | None = None,
    skill_videos: list[dict] | None = None,
    skill_readings: list[dict] | None = None,
    resource_df: pd.DataFrame | None = None,
) -> Path:
    """Save training artefacts to data/synthgen/<run_id>/."""
    out = cfg.out_dir / cfg.run_id
    out.mkdir(parents=True, exist_ok=True)

    # Build IndexMapper-compatible vocab.json
    student_ids = sorted({s["student_id"] for s in students})
    question_ids = sorted({q["question_id"] for q in questions})
    skill_names = sorted({s["name"] for s in skills})

    # Map synth IDs → postgres IDs for the "user" namespace
    pg_ids_ordered = [pg_id_map[sid] for sid in student_ids]

    # Build video / reading vocab from edge lists
    video_ids_ordered: list[str] = []
    reading_ids_ordered: list[str] = []
    if skill_videos:
        video_ids_ordered = sorted({e["video_id"] for e in skill_videos if e.get("video_id")})
    if skill_readings:
        reading_ids_ordered = sorted({e["reading_id"] for e in skill_readings if e.get("reading_id")})

    vocab: dict = {
        "user": {str(pg_id): idx for idx, pg_id in enumerate(pg_ids_ordered)},
        "question": {qid: idx for idx, qid in enumerate(question_ids)},
        "concept": {sn: idx for idx, sn in enumerate(skill_names)},
    }
    if video_ids_ordered:
        vocab["video"] = {vid: idx for idx, vid in enumerate(video_ids_ordered)}
    if reading_ids_ordered:
        vocab["reading"] = {rid: idx for idx, rid in enumerate(reading_ids_ordered)}

    (out / "vocab.json").write_text(json.dumps(vocab, indent=2))
    logger.info(
        "Saved vocab.json (%d users, %d questions, %d skills, %d videos, %d readings)",
        len(pg_ids_ordered), len(question_ids), len(skill_names),
        len(video_ids_ordered), len(reading_ids_ordered),
    )

    # Bridge file: synth UUID → student_idx (needed to look up mastery in training)
    student_id_to_idx = {sid: idx for idx, sid in enumerate(student_ids)}
    (out / "student_id_to_idx.json").write_text(json.dumps(student_id_to_idx))

    # ── KG edge parquets ───────────────────────────────────────────────────
    skill_idx = vocab["concept"]

    if prereq_edges:
        prereq_rows = []
        for e in prereq_edges:
            src_i = skill_idx.get(e.get("from_skill", ""), -1)
            dst_i = skill_idx.get(e.get("to_skill", ""), -1)
            if src_i >= 0 and dst_i >= 0:
                prereq_rows.append({
                    "src_skill_idx": src_i,
                    "dst_skill_idx": dst_i,
                    "strength": float(e.get("strength", 1.0)),
                })
        if prereq_rows:
            pd.DataFrame(prereq_rows).to_parquet(out / "prereq_edges.parquet", index=False)
            logger.info("Saved prereq_edges.parquet (%d edges)", len(prereq_rows))

    if skill_videos and video_ids_ordered:
        video_idx = vocab["video"]
        sv_rows = []
        for e in skill_videos:
            si = skill_idx.get(e.get("skill_name", ""), -1)
            vi = video_idx.get(e.get("video_id", ""), -1)
            if si >= 0 and vi >= 0:
                sv_rows.append({"skill_idx": si, "video_idx": vi})
        if sv_rows:
            pd.DataFrame(sv_rows).drop_duplicates().to_parquet(
                out / "skill_videos.parquet", index=False
            )
            logger.info("Saved skill_videos.parquet (%d edges)", len(sv_rows))

    if skill_readings and reading_ids_ordered:
        reading_idx = vocab["reading"]
        sr_rows = []
        for e in skill_readings:
            si = skill_idx.get(e.get("skill_name", ""), -1)
            ri = reading_idx.get(e.get("reading_id", ""), -1)
            if si >= 0 and ri >= 0:
                sr_rows.append({"skill_idx": si, "reading_idx": ri})
        if sr_rows:
            pd.DataFrame(sr_rows).drop_duplicates().to_parquet(
                out / "skill_readings.parquet", index=False
            )
            logger.info("Saved skill_readings.parquet (%d edges)", len(sr_rows))

    # Encode indices into the interactions DataFrame
    user_enc = vocab["user"]
    q_enc = vocab["question"]
    s_enc = vocab["concept"]
    v_enc = vocab.get("video", {})
    r_enc = vocab.get("reading", {})

    # ── Question events (event_type=0) ────────────────────────────────────
    q_df = interactions_df.copy()
    q_df["pg_id"] = q_df["student_id"].map(pg_id_map)
    q_df["student_idx"] = q_df["pg_id"].map(lambda x: user_enc.get(str(x), -1))
    q_df["entity_idx"] = q_df["question_id"].map(lambda x: q_enc.get(x, -1))
    q_df["skill_idx"] = q_df["skill_id"].map(lambda x: s_enc.get(x, -1))
    q_df["event_type"] = 0
    q_df["correct"] = q_df["correct"].astype(float)
    q_df["score"] = q_df["score"].astype(float)
    q_df["attempt_num"] = q_df["attempt_num"].astype(int)
    q_df["is_repeat"] = q_df["is_repeat"].astype(bool)

    before = len(q_df)
    q_df = q_df[
        (q_df["student_idx"] >= 0)
        & (q_df["entity_idx"] >= 0)
        & (q_df["skill_idx"] >= 0)
    ]
    if len(q_df) < before:
        logger.warning("Dropped %d question rows with unmapped IDs", before - len(q_df))

    parquet_cols = [
        "student_idx", "event_type", "entity_idx", "skill_idx",
        "correct", "score", "timestamp_sec", "attempt_num", "is_repeat",
    ]
    q_events = q_df[parquet_cols].copy()

    # ── Resource events (event_type=1 video, =2 reading) ──────────────────
    # Build resource_id → first skill_name lookup so each resource event has
    # a skill_idx for KG attribution.
    resource_to_skill: dict[str, str] = {}
    if skill_videos:
        for e in skill_videos:
            vid = e.get("video_id")
            sk = e.get("skill_name")
            if vid and sk and vid not in resource_to_skill:
                resource_to_skill[vid] = sk
    if skill_readings:
        for e in skill_readings:
            rid = e.get("reading_id")
            sk = e.get("skill_name")
            if rid and sk and rid not in resource_to_skill:
                resource_to_skill[rid] = sk

    resource_events_rows: list[dict] = []
    if resource_df is not None and len(resource_df) > 0:
        for row in resource_df.itertuples(index=False):
            sid = row.student_id
            pg_id = pg_id_map.get(sid)
            if pg_id is None:
                continue
            student_idx = user_enc.get(str(pg_id), -1)
            if student_idx < 0:
                continue

            rtype = row.resource_type
            rid = row.resource_id
            if rtype == "video":
                event_type = 1
                entity_idx = v_enc.get(rid, -1)
            elif rtype == "reading":
                event_type = 2
                entity_idx = r_enc.get(rid, -1)
            else:
                continue
            if entity_idx < 0:
                continue

            skill_name = resource_to_skill.get(rid)
            skill_idx = s_enc.get(skill_name, -1) if skill_name else -1
            if skill_idx < 0:
                continue

            for ts in row.opened_at_sec:
                resource_events_rows.append(
                    {
                        "student_idx": int(student_idx),
                        "event_type": int(event_type),
                        "entity_idx": int(entity_idx),
                        "skill_idx": int(skill_idx),
                        # Engagement signal: opened = 1 (no correctness label)
                        "correct": 1.0,
                        "score": 1.0,
                        "timestamp_sec": int(ts),
                        "attempt_num": 1,
                        "is_repeat": False,
                    }
                )

    if resource_events_rows:
        r_events = pd.DataFrame(resource_events_rows, columns=parquet_cols)
        all_events = pd.concat([q_events, r_events], ignore_index=True)
    else:
        all_events = q_events

    n_q = int((all_events["event_type"] == 0).sum())
    n_v = int((all_events["event_type"] == 1).sum())
    n_r = int((all_events["event_type"] == 2).sum())
    logger.info(
        "Unified events: %d total (%d question / %d video / %d reading)",
        len(all_events), n_q, n_v, n_r,
    )

    df_sorted = all_events.sort_values("timestamp_sec").reset_index(drop=True)
    split_idx = int(len(df_sorted) * cfg.train_ratio)
    train_df = df_sorted.iloc[:split_idx].copy()
    test_df = df_sorted.iloc[split_idx:].copy()

    train_df.to_parquet(out / "train.parquet", index=False)
    test_df.to_parquet(out / "test.parquet", index=False)
    mastery_df.to_parquet(out / "mastery_ground_truth.parquet", index=False)

    # Save run metadata
    meta = {
        "run_id": cfg.run_id,
        "n_students": cfg.n_students,
        "n_questions": len(questions),
        "n_skills": len(skills),
        "n_videos": len(video_ids_ordered),
        "n_readings": len(reading_ids_ordered),
        "total_interactions": len(all_events),
        "n_question_events": n_q,
        "n_video_events": n_v,
        "n_reading_events": n_r,
        "train_interactions": len(train_df),
        "test_interactions": len(test_df),
        "train_ratio": cfg.train_ratio,
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2))

    logger.info(
        "Saved parquet artifacts to %s  (train=%d test=%d)",
        out, len(train_df), len(test_df),
    )
    return out
