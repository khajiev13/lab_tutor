"""
src/dataset/loaders/xes3g5m.py — XES3G5M dataset loader.

XES3G5M is the primary benchmark for ARCD. It uses the standard 5-column
CSV format expected by TemporalProcessor.
"""

from __future__ import annotations

import pandas as pd
from src.dataset.loaders.base import BaseDatasetLoader
from src.preprocessing.index_mapper import IndexMapper
from src.preprocessing.temporal_processor import TemporalProcessor


class XES3G5MLoader(BaseDatasetLoader):
    """Loader for the XES3G5M knowledge-tracing dataset.

    Expected directory layout::

        raw_dir/
            extracted/XES3G5M/
                train_valid_sequences_quelevel.csv
                test_sequences_quelevel.csv

    Args:
        raw_dir: Root of the XES3G5M raw data directory.
        split:   ``"all"`` (default), ``"train"``, ``"valid"``, or ``"test"``.
    """

    _SPLIT_FILES = {
        "train": "train_valid_sequences_quelevel.csv",
        "valid": "train_valid_sequences_quelevel.csv",
        "test":  "test_sequences_quelevel.csv",
    }

    @property
    def name(self) -> str:
        return "xes3g5m"

    def _csv_paths(self, for_all: bool = False):
        base = self.raw_dir / "extracted" / "XES3G5M"
        if not base.exists():
            base = self.raw_dir  # fallback: raw_dir already points at the right folder
        if for_all or self.split == "all":
            return sorted({base / f for f in self._SPLIT_FILES.values()})
        fname = self._SPLIT_FILES.get(self.split, self._SPLIT_FILES["train"])
        return [base / fname]

    def fit_mapper(self) -> IndexMapper:
        """Scan all CSVs (both splits) to build a complete index mapping."""
        return TemporalProcessor.fit_mapper(self._csv_paths(for_all=True))

    def extract_to_dataframe(self, mapper: IndexMapper) -> pd.DataFrame:
        """Build interaction DataFrame from the selected split(s)."""
        return TemporalProcessor.extract_to_dataframe(self._csv_paths(), mapper)
