"""
src/dataset/loaders/ednet.py — EdNet dataset loader.

EdNet is a large-scale Korean K-12 dataset (7M+ students). Its raw format
consists of per-student CSV files in nested directories. This loader expects
either the full raw format or the pre-merged 5-column CSV.
"""

from __future__ import annotations

import pandas as pd
from src.dataset.loaders.base import BaseDatasetLoader
from src.preprocessing.index_mapper import IndexMapper
from src.preprocessing.temporal_processor import TemporalProcessor


class EdNetLoader(BaseDatasetLoader):
    """Loader for the EdNet dataset.

    Supports two layouts:

    1. **Pre-merged** (recommended): A single 5-column CSV in ``raw_dir/``:
       ``ednet_merged.csv`` (or whatever ``merged_file`` is set to).

    2. **Raw**: Per-student CSVs under ``raw_dir/KT1/`` — merged on-the-fly.

    Args:
        raw_dir:     Root of the EdNet raw data directory.
        split:       ``"all"`` (default), ``"train"``, or ``"test"``.
        merged_file: Name of the pre-merged CSV (used if it exists).
        max_students: Maximum number of students to load when using raw mode
                      (None = all). Useful for quick experiments.
    """

    def __init__(
        self,
        raw_dir,
        split: str = "all",
        merged_file: str = "ednet_merged.csv",
        max_students: int | None = None,
    ):
        super().__init__(raw_dir, split)
        self._merged_file = merged_file
        self._max_students = max_students

    @property
    def name(self) -> str:
        return "ednet"

    def _csv_paths(self, for_all: bool = False):
        merged = self.raw_dir / self._merged_file
        if merged.exists():
            return [merged]
        # Fallback: look for any CSV in raw_dir
        csvs = sorted(self.raw_dir.glob("*.csv"))
        if not csvs:
            # Last resort: KT1 subdirectory (original EdNet format)
            kt1 = self.raw_dir / "KT1"
            if kt1.exists():
                csvs = sorted(kt1.glob("u*.csv"))
                if self._max_students:
                    csvs = csvs[: self._max_students]
        return csvs

    def fit_mapper(self) -> IndexMapper:
        return TemporalProcessor.fit_mapper(self._csv_paths(for_all=True))

    def extract_to_dataframe(self, mapper: IndexMapper) -> pd.DataFrame:
        return TemporalProcessor.extract_to_dataframe(self._csv_paths(), mapper)
