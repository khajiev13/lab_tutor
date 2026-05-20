"""Summarize repeated job-fit evaluation runs across LLM judges."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


PORTFOLIOS = ("course_only", "book_student", "market_student")
SUMMARY_FIELDS = [
    "run_name",
    "family",
    "model",
    "n_calls",
    "n_paired_jobs",
    "course_only_mean",
    "book_student_mean",
    "market_student_mean",
    "market_minus_course_mean",
    "market_gt_course_jobs",
    "market_eq_course_jobs",
    "market_lt_course_jobs",
    "market_rank",
    "ranking",
    "source_dir",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def infer_family(model: str, run_name: str) -> str:
    value = f"{model} {run_name}".lower()
    if "deepseek" in value:
        return "DeepSeek"
    if "qwen" in value:
        return "Qwen"
    if "glm" in value:
        return "GLM"
    if "kimi" in value:
        return "Kimi"
    if "minimax" in value:
        return "MiniMax"
    return "Unknown"


def load_metadata(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "run_metadata.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def rank_portfolios(means: dict[str, float]) -> tuple[str, int]:
    ordered = sorted(PORTFOLIOS, key=lambda name: (-means.get(name, 0.0), name))
    rank_lookup = {name: index + 1 for index, name in enumerate(ordered)}
    return ">".join(ordered), rank_lookup["market_student"]


def summarize_run(run_dir: Path) -> dict[str, Any]:
    summary_csv = run_dir / "job_satisfaction_summary.csv"
    if not summary_csv.exists():
        summary_csv = run_dir / "outputs" / "job_satisfaction_summary.csv"
    if not summary_csv.exists():
        raise FileNotFoundError(summary_csv)

    rows = read_csv(summary_csv)
    metadata = load_metadata(run_dir)
    run_name = run_dir.name
    model = str(metadata.get("model") or "")
    family = str(metadata.get("family") or infer_family(model, run_name))

    by_portfolio: dict[str, list[float]] = {name: [] for name in PORTFOLIOS}
    paired: dict[tuple[str, str], dict[str, float]] = {}
    for row in rows:
        portfolio = row["portfolio"]
        if portfolio not in by_portfolio:
            continue
        score = float(row["satisfaction_score"])
        by_portfolio[portfolio].append(score)
        key = (row["job_title"], row["job_company"])
        paired.setdefault(key, {})[portfolio] = score

    means = {name: round(mean(scores), 4) for name, scores in by_portfolio.items()}
    deltas: list[float] = []
    gt = eq = lt = 0
    for scores in paired.values():
        if "market_student" not in scores or "course_only" not in scores:
            continue
        delta = scores["market_student"] - scores["course_only"]
        deltas.append(delta)
        if delta > 0:
            gt += 1
        elif delta < 0:
            lt += 1
        else:
            eq += 1

    ranking, market_rank = rank_portfolios(means)
    return {
        "run_name": run_name,
        "family": family,
        "model": model,
        "n_calls": len(rows),
        "n_paired_jobs": len(deltas),
        "course_only_mean": means["course_only"],
        "book_student_mean": means["book_student"],
        "market_student_mean": means["market_student"],
        "market_minus_course_mean": round(mean(deltas), 4),
        "market_gt_course_jobs": gt,
        "market_eq_course_jobs": eq,
        "market_lt_course_jobs": lt,
        "market_rank": market_rank,
        "ranking": ranking,
        "source_dir": str(run_dir),
    }


def collect_runs(runs_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for run_dir in sorted(path for path in runs_dir.iterdir() if path.is_dir()):
        summary_csv = run_dir / "job_satisfaction_summary.csv"
        nested_summary_csv = run_dir / "outputs" / "job_satisfaction_summary.csv"
        if summary_csv.exists() or nested_summary_csv.exists():
            rows.append(summarize_run(run_dir))
    return rows


def write_summary_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def latex_escape(value: object) -> str:
    return str(value).replace("\\", "\\textbackslash{}").replace("_", "\\_").replace("&", "\\&")


def write_latex_table(rows: list[dict[str, Any]], path: Path) -> None:
    lines = [
        "\\begin{table}[t]",
        "\\caption{Robustness of portfolio satisfaction results across LLM judges.}",
        "\\label{tab:judge-robustness}",
        "\\centering",
        "\\begin{tabular}{lrrrrr}",
        "\\hline",
        "Judge & Course & Book & Market & $\\Delta$ M-C & M$>$C \\\\",
        "\\hline",
    ]
    for row in rows:
        judge = f"{row['family']} ({row['model']})" if row["model"] else row["family"]
        lines.append(
            f"{latex_escape(judge)} & "
            f"{row['course_only_mean']:.3f} & "
            f"{row['book_student_mean']:.3f} & "
            f"{row['market_student_mean']:.3f} & "
            f"{row['market_minus_course_mean']:.3f} & "
            f"{row['market_gt_course_jobs']}/{row['n_paired_jobs']} \\\\"
        )
    lines.extend(["\\hline", "\\end{tabular}", "\\end{table}", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--output-tex", type=Path, required=True)
    args = parser.parse_args()

    rows = collect_runs(args.runs_dir)
    if not rows:
        raise SystemExit(f"No completed runs found in {args.runs_dir}")
    write_summary_csv(rows, args.output_csv)
    write_latex_table(rows, args.output_tex)
    print(f"Wrote {args.output_csv}")
    print(f"Wrote {args.output_tex}")


if __name__ == "__main__":
    main()
