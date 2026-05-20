from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
EVALUATION_DIR = THIS_DIR.parent
sys.path.insert(0, str(THIS_DIR))

import run_job_fit_evaluation as runner  # noqa: E402
import summarize_judge_robustness as robustness  # noqa: E402


def test_frozen_input_matches_thesis_protocol() -> None:
    bundle = runner.load_input_bundle(EVALUATION_DIR / "input" / "job_fit_inputs.json")

    portfolios = {item["name"]: item for item in bundle["portfolios"]}
    assert sorted(portfolios) == ["book_student", "course_only", "market_student"]
    assert len(portfolios["course_only"]["skills"]) == 100
    assert len(portfolios["book_student"]["skills"]) == 121
    assert len(portfolios["market_student"]["skills"]) == 134

    jobs = bundle["jobs"]
    assert len(jobs) == 25
    assert sum(len(job["required_skills"]) for job in jobs) == 158


def test_score_ratings_uses_requirement_weights() -> None:
    requirements = ["SQL", "Airflow", "Kubernetes"]
    ratings = [
        {"requirement": "SQL", "label": "fully_satisfied", "evidence_skills": ["SQL"], "justification": "Direct match."},
        {"requirement": "Airflow", "label": "satisfied", "evidence_skills": ["Apache Airflow"], "justification": "Equivalent tool."},
        {"requirement": "Kubernetes", "label": "not_satisfied", "evidence_skills": [], "justification": "Missing."},
    ]

    score, counts, rows = runner.score_ratings(requirements, ratings)

    assert score == 0.5833
    assert counts == {
        "fully_satisfied": 1,
        "satisfied": 1,
        "partly_satisfied": 0,
        "not_satisfied": 1,
    }
    assert [row["weight"] for row in rows] == [1.0, 0.75, 0.0]


def test_summarize_expected_outputs_report_market_advantage(tmp_path: Path) -> None:
    run_dir = tmp_path / "qwen"
    run_dir.mkdir()
    (run_dir / "run_metadata.json").write_text(
        json.dumps({"family": "Qwen", "model": "qwen3.6-plus"}),
        encoding="utf-8",
    )
    with (run_dir / "job_satisfaction_summary.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "portfolio",
                "job_title",
                "job_company",
                "n_required_skills",
                "n_fully_satisfied",
                "n_satisfied",
                "n_partly_satisfied",
                "n_not_satisfied",
                "satisfaction_score",
            ],
        )
        writer.writeheader()
        for portfolio, score in [
            ("course_only", "0.5000"),
            ("book_student", "0.6000"),
            ("market_student", "0.9000"),
        ]:
            writer.writerow(
                {
                    "portfolio": portfolio,
                    "job_title": "Data Engineer",
                    "job_company": "Example Co",
                    "n_required_skills": "1",
                    "n_fully_satisfied": "0",
                    "n_satisfied": "0",
                    "n_partly_satisfied": "0",
                    "n_not_satisfied": "1",
                    "satisfaction_score": score,
                }
            )

    summary = robustness.summarize_run(run_dir)

    assert summary["family"] == "Qwen"
    assert summary["model"] == "qwen3.6-plus"
    assert summary["course_only_mean"] == 0.5
    assert summary["market_student_mean"] == 0.9
    assert summary["market_minus_course_mean"] == 0.4
    assert summary["market_gt_course_jobs"] == 1
    assert summary["market_rank"] == 1
