"""synthgen.__main__ — CLI entry point.

Usage:
    cd knowledge_graph_builder
    uv run python -m synthgen [options]

Options:
    --n-students INT          Number of synthetic students (default: 1000)
    --target-interactions INT Target interaction count (default: 500000)
    --teacher-username STR    Teacher to look up in Postgres (default: Roma)
    --run-id STR              Custom run ID (auto-generated if omitted)
    --seed INT                Random seed (default: 42)
    --dry-run                 Skip DB writes; only generate + save parquet
    --skip-questions          Skip question generation (use existing)
    --skip-neo4j-students     Skip writing student nodes to Neo4j
    --skip-neo4j-interactions Skip writing ANSWERED/MASTERED edges
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# Allow running as `python -m synthgen` from knowledge_graph_builder/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from synthgen.config import default_config
from synthgen.exporter import (
    enroll_students_in_classes,
    save_parquet_artifacts,
    write_answered_edges,
    write_mastery_to_neo4j,
    write_resource_edges,
    write_selected_skill_edges,
    write_student_nodes_to_neo4j,
    write_students_to_postgres,
)
from synthgen.interaction_simulator import (
    compute_mastery_ground_truth,
    simulate_interactions,
    simulate_resource_interactions,
)
from synthgen.kg_extraction import (
    fetch_existing_questions,
    fetch_prerequisite_edges,
    fetch_skill_reading_edges,
    fetch_skill_video_edges,
    fetch_skills,
)
from synthgen.question_generator import build_question_bank, write_questions_to_neo4j
from synthgen.roma_lookup import (
    lookup_or_create_teacher,
    lookup_skills_for_class,
    lookup_teacher_classes,
)
from synthgen.student_generator import generate_students


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
        level=level,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m synthgen",
        description="Generate synthetic students & interactions for Lab Tutor validation.",
    )
    parser.add_argument("--n-students", type=int, default=1000)
    parser.add_argument("--target-interactions", type=int, default=500_000)
    parser.add_argument("--teacher-username", type=str, default="Roma")
    parser.add_argument("--run-id", type=str, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-student-skills", type=int, default=15,
                        help="Minimum skills per student (default: 15)")
    parser.add_argument("--max-student-skills", type=int, default=25,
                        help="Maximum skills per student (default: 25)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip DB writes; only generate parquet artifacts")
    parser.add_argument("--skip-questions", action="store_true",
                        help="Skip question generation; use existing questions")
    parser.add_argument("--skip-neo4j-students", action="store_true")
    parser.add_argument("--skip-neo4j-interactions", action="store_true")
    parser.add_argument(
        "--skip-neo4j-resources", action="store_true",
        help="Skip writing OPENED_VIDEO / OPENED_READING edges",
    )
    parser.add_argument(
        "--all-skills", action="store_true",
        help=(
            "Use ALL skills in the knowledge graph (SKILL + BOOK_SKILL + MARKET_SKILL) "
            "instead of only the skills from the teacher's class. "
            "Required to capture the full 423-skill Neo4j graph."
        ),
    )
    parser.add_argument(
        "--video-open-prob", type=float, default=None,
        help="Override base probability a student opens a video (default from config)",
    )
    parser.add_argument(
        "--reading-open-prob", type=float, default=None,
        help="Override base probability a student opens a reading (default from config)",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    _setup_logging(args.verbose)
    logger = logging.getLogger("synthgen")

    cfg = default_config(
        n_students=args.n_students,
        target_interactions=args.target_interactions,
        teacher_username=args.teacher_username,
        random_seed=args.seed,
        min_student_skills=args.min_student_skills,
        max_student_skills=args.max_student_skills,
    )
    if args.run_id:
        cfg.run_id = args.run_id
    if args.video_open_prob is not None:
        cfg.video_open_prob = args.video_open_prob
    if args.reading_open_prob is not None:
        cfg.reading_open_prob = args.reading_open_prob

    t0 = time.time()
    logger.info("=" * 60)
    logger.info("synthgen — run_id: %s", cfg.run_id)
    logger.info("  n_students            : %d", cfg.n_students)
    logger.info("  target_interactions   : %d", cfg.target_interactions)
    logger.info("  teacher               : %s", cfg.teacher_username)
    logger.info("  dry_run               : %s", args.dry_run)
    logger.info("=" * 60)

    # ── 1. Connect to Neo4j ──────────────────────────────────────────────
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        cfg.neo4j_uri, auth=(cfg.neo4j_user, cfg.neo4j_password)
    )

    with driver.session(database=cfg.neo4j_database) as neo4j_session:

        # ── 2. Resolve teacher & classes ─────────────────────────────────
        logger.info("Resolving teacher '%s' …", cfg.teacher_username)
        if args.dry_run:
            # In dry-run, use first available teacher from Neo4j
            r = neo4j_session.run(
                "MATCH (u:USER:TEACHER)-[:TEACHES_CLASS]->(c:CLASS) "
                "RETURN u.id AS id, u.email AS email, "
                "       u.first_name AS first_name, u.last_name AS last_name "
                "LIMIT 1"
            ).single()
            if r:
                teacher = dict(r)
                logger.info("Dry-run: using teacher %s", teacher)
            else:
                teacher = {"id": 1, "email": "teacher@example.com",
                           "first_name": "Teacher", "last_name": "One"}
                logger.info("Dry-run: using fallback teacher")
        else:
            teacher = lookup_or_create_teacher(
                cfg.postgres_url, neo4j_session, cfg.teacher_username
            )
        classes = lookup_teacher_classes(neo4j_session, teacher["id"])

        if not classes:
            logger.warning(
                "Teacher %s (id=%s) has no classes in Neo4j. "
                "Students will still be created but not enrolled.",
                cfg.teacher_username,
                teacher["id"],
            )

        class_ids = [int(c["id"]) for c in classes]

        # ── 3. Fetch skills ──────────────────────────────────────────────
        if args.all_skills:
            logger.info("--all-skills: fetching ALL skills from Neo4j graph …")
            skills = fetch_skills(neo4j_session)
        elif classes:
            # Prefer skills from the first class for consistency
            skills = lookup_skills_for_class(neo4j_session, class_ids[0])
        else:
            skills = []

        if not args.all_skills and (not classes or not skills):
            logger.info("Falling back to all skills in graph …")
            skills = fetch_skills(neo4j_session)

        if not skills:
            logger.error("No skills found in the graph. Cannot proceed.")
            sys.exit(1)
        logger.info("Using %d skills", len(skills))

        # ── 3b. Fetch KG edges from existing graph ───────────────────────
        logger.info("Fetching prerequisite edges from Neo4j …")
        prereq_edges = fetch_prerequisite_edges(neo4j_session)

        logger.info("Fetching skill-video edges from Neo4j …")
        skill_videos = fetch_skill_video_edges(neo4j_session)

        logger.info("Fetching skill-reading edges from Neo4j …")
        skill_readings = fetch_skill_reading_edges(neo4j_session)

        # ── 4. Build question bank ───────────────────────────────────────
        if not args.skip_questions:
            questions = build_question_bank(skills, cfg)
            if not args.dry_run:
                logger.info("Writing %d questions to Neo4j …", len(questions))
                write_questions_to_neo4j(questions, neo4j_session, cfg)
        else:
            logger.info("Fetching existing questions from Neo4j …")
            existing = fetch_existing_questions(neo4j_session)
            if existing:
                questions = [
                    {
                        "question_id": q["id"],
                        "skill_ids": q["skill_names"],
                        "difficulty": q["difficulty"],
                        "discrimination": q["discrimination"],
                    }
                    for q in existing
                ]
            else:
                logger.info("No existing questions; building fresh bank …")
                questions = build_question_bank(skills, cfg)
                if not args.dry_run:
                    write_questions_to_neo4j(questions, neo4j_session, cfg)

        logger.info("Question bank: %d questions", len(questions))

        # ── 5. Generate students ─────────────────────────────────────────
        logger.info("Generating %d students …", cfg.n_students)
        students = generate_students(cfg)

        # ── 6. Postgres: create user rows ────────────────────────────────
        pg_id_map: dict[str, int] = {}
        if not args.dry_run:
            logger.info("Writing students to Postgres …")
            pg_id_map = write_students_to_postgres(students, cfg)
        else:
            # Fake IDs for dry-run
            for i, s in enumerate(students):
                pg_id_map[s["student_id"]] = -(i + 1)

        # ── 7. Neo4j: write student nodes & enroll ───────────────────────
        if not args.dry_run and not args.skip_neo4j_students:
            logger.info("Writing student nodes to Neo4j …")
            write_student_nodes_to_neo4j(students, pg_id_map, neo4j_session, cfg)
            if class_ids:
                logger.info("Enrolling students in %d classes …", len(class_ids))
                enroll_students_in_classes(pg_id_map, class_ids, neo4j_session, cfg)

        # ── 8. Simulate interactions ─────────────────────────────────────
        logger.info(
            "Simulating interactions (target=%d, skills per student: %d–%d) …",
            cfg.target_interactions,
            cfg.min_student_skills,
            cfg.max_student_skills,
        )
        interactions_df = simulate_interactions(students, questions, cfg)
        logger.info("Total interactions generated: %d", len(interactions_df))

        # Build per-student skill selection map for Neo4j export
        student_skills_map: dict[str, set[str]] = {
            s["student_id"]: set(s.get("selected_skills", []))
            for s in students
        }

        # ── 8b. Simulate resource interactions ───────────────────────────
        logger.info(
            "Simulating resource opens "
            "(video_prob=%.2f, reading_prob=%.2f) …",
            cfg.video_open_prob,
            cfg.reading_open_prob,
        )
        resource_df = simulate_resource_interactions(
            students, skill_videos, skill_readings, interactions_df, cfg
        )
        logger.info("Total resource interaction rows: %d", len(resource_df))

        # ── 9. Compute mastery ground truth ──────────────────────────────
        logger.info("Computing mastery ground truth …")
        mastery_df = compute_mastery_ground_truth(
            students, questions, interactions_df, cfg
        )

        # ── 10. Save parquet artifacts ───────────────────────────────────
        logger.info("Saving parquet artifacts …")
        out_dir = save_parquet_artifacts(
            interactions_df, mastery_df, students, questions, skills,
            pg_id_map, cfg,
            prereq_edges=prereq_edges,
            skill_videos=skill_videos,
            skill_readings=skill_readings,
            resource_df=resource_df,
        )
        logger.info("Artifacts saved to: %s", out_dir)

        # ── 11. Write interactions to Neo4j ──────────────────────────────
        if not args.dry_run and not args.skip_neo4j_interactions:
            logger.info("Writing ANSWERED edges to Neo4j …")
            write_answered_edges(interactions_df, pg_id_map, neo4j_session, cfg)

            logger.info("Writing MASTERED edges to Neo4j …")
            write_mastery_to_neo4j(mastery_df, pg_id_map, neo4j_session, cfg)

            logger.info("Writing SELECTED_SKILL edges to Neo4j …")
            write_selected_skill_edges(
                mastery_df, pg_id_map, neo4j_session, cfg,
                student_skills_map=student_skills_map,
            )

        # ── 12. Write resource edges to Neo4j ────────────────────────────
        if not args.dry_run and not args.skip_neo4j_resources:
            if not resource_df.empty:
                logger.info("Writing OPENED_VIDEO / OPENED_READING edges to Neo4j …")
                write_resource_edges(resource_df, pg_id_map, neo4j_session, cfg)
            else:
                logger.info(
                    "No resource interactions generated; "
                    "skipping OPENED_VIDEO / OPENED_READING writes."
                )

    driver.close()

    elapsed = time.time() - t0
    logger.info("=" * 60)
    logger.info("synthgen COMPLETE in %.1fs — run_id: %s", elapsed, cfg.run_id)
    logger.info("  Parquet artifacts : %s", out_dir)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
