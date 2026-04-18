from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pandas as pd

from .index_mapper import IndexMapper

_REQUIRED_CSV_COLUMNS = frozenset(
    {"uid", "questions", "concepts", "responses", "timestamps"}
)


def _validate_csv_columns(reader: csv.DictReader, path: Path) -> None:
    """Raise ValueError if required columns are missing."""
    if reader.fieldnames is None:
        raise ValueError(f"CSV has no header: {path}")
    missing = _REQUIRED_CSV_COLUMNS - set(reader.fieldnames)
    if missing:
        raise ValueError(f"CSV missing required columns {sorted(missing)} in {path}")


class TemporalProcessor:
    """Array-native preprocessor for XES3G5M-format CSVs.

    Two-step workflow:
        1. fit_mapper(all_csv_paths) — lightweight scan to collect unique IDs
        2. extract_to_dataframe(split_paths, mapper) — build sorted DataFrame
    """

    @staticmethod
    def fit_mapper(csv_paths: list[Path]) -> IndexMapper:
        """Scan CSVs to collect all unique IDs and fit an IndexMapper."""
        users: set[str] = set()
        questions: set[str] = set()
        concepts: set[str] = set()

        for path in csv_paths:
            with open(path) as f:
                reader = csv.DictReader(f)
                _validate_csv_columns(reader, path)
                for row in reader:
                    users.add(row["uid"])
                    for q in row["questions"].split(","):
                        q = q.strip()
                        if q != "-1":
                            questions.add(q)
                    for cg in row["concepts"].split(","):
                        cg = cg.strip()
                        if cg != "-1":
                            for c in cg.split("_"):
                                concepts.add(c)

        mapper = IndexMapper()
        mapper.fit("user", list(users))
        mapper.fit("question", list(questions))
        mapper.fit("concept", list(concepts))
        return mapper

    @staticmethod
    def extract_to_dataframe(
        csv_paths: list[Path],
        mapper: IndexMapper,
    ) -> pd.DataFrame:
        """Parse CSVs into a sorted DataFrame using a pre-fitted mapper.

        Builds column arrays directly — no intermediate Python objects.
        Returns DataFrame sorted by (student_idx, t_sec) with columns:
            student_idx (int32), question_idx (int32), skill_idx (int32),
            all_skill_indices (str), correct (int8), t_sec (float64)
        """
        student_col: list[int] = []
        question_col: list[int] = []
        skill_col: list[int] = []
        all_skills_col: list[str] = []
        correct_col: list[int] = []
        tsec_col: list[float] = []

        for path in csv_paths:
            with open(path) as f:
                reader = csv.DictReader(f)
                _validate_csv_columns(reader, path)
                raw_rows = [
                    (
                        row["uid"],
                        row["questions"],
                        row["concepts"],
                        row["responses"],
                        row["timestamps"],
                    )
                    for row in reader
                ]
            _expand_rows(
                raw_rows,
                mapper,
                student_col,
                question_col,
                skill_col,
                all_skills_col,
                correct_col,
                tsec_col,
            )

        df = pd.DataFrame(
            {
                "student_idx": np.array(student_col, dtype=np.int32),
                "question_idx": np.array(question_col, dtype=np.int32),
                "skill_idx": np.array(skill_col, dtype=np.int32),
                "all_skill_indices": all_skills_col,
                "correct": np.array(correct_col, dtype=np.int8),
                "t_sec": np.array(tsec_col, dtype=np.float64),
            }
        )

        df.sort_values(["student_idx", "t_sec"], inplace=True, ignore_index=True)
        return df

    # Backward compat alias
    scan_csv_ids = fit_mapper


def _expand_rows(
    raw_rows: list[tuple[str, str, str, str, str]],
    mapper: IndexMapper,
    student_col: list[int],
    question_col: list[int],
    skill_col: list[int],
    all_skills_col: list[str],
    correct_col: list[int],
    tsec_col: list[float],
) -> None:
    """Explode pre-grouped rows into flat column lists (hot loop)."""
    user_map = mapper._maps["user"]
    q_map = mapper._maps["question"]
    c_map = mapper._maps["concept"]

    for uid, qs_str, cs_str, rs_str, ts_str in raw_rows:
        sidx = user_map.get(uid)
        if sidx is None:
            raise ValueError(
                f"Unknown uid {uid!r} not seen during fit_mapper; ensure extract_to_dataframe uses the same CSV set as fit_mapper."
            )

        qs = [x.strip() for x in qs_str.split(",")]
        cs = [x.strip() for x in cs_str.split(",")]
        rs = [x.strip() for x in rs_str.split(",")]
        ts = [x.strip() for x in ts_str.split(",")]
        if not (len(qs) == len(cs) == len(rs) == len(ts)):
            raise ValueError(
                f"Mismatched lengths in row (uid={uid!r}): questions={len(qs)}, concepts={len(cs)}, responses={len(rs)}, timestamps={len(ts)}. "
                "Ensure each row has the same number of comma-separated values in these columns."
            )

        for q, cg, r, t in zip(qs, cs, rs, ts, strict=False):
            if q == "-1":
                continue
            if r == "-1":
                continue
            if t == "-1":
                continue

            qidx = q_map.get(q)
            if qidx is None:
                raise ValueError(
                    f"Unknown question id {q!r} not seen during fit_mapper; ensure extract_to_dataframe uses the same CSV set as fit_mapper."
                )

            student_col.append(sidx)
            question_col.append(qidx)

            skills = []
            for c in cg.strip().split("_"):
                idx = c_map.get(c)
                if idx is not None:
                    skills.append(idx)

            skill_col.append(skills[0] if skills else -1)
            all_skills_col.append("_".join(str(s) for s in skills) if skills else "")
            correct_col.append(int(r))
            tsec_col.append(int(t) / 1000.0)
