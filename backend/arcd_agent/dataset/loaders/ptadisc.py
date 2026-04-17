"""
src/dataset/loaders/ptadisc.py — PTADisc dataset loader.

PTADisc (Paper-Test Adaptive Discovery of Student Concepts) is a
college-level Chinese math dataset. Its raw format is a series of
per-student JSON or CSV files; this loader expects the pre-extracted
5-column CSV format produced by preprocessing notebooks.
"""

from __future__ import annotations

import pandas as pd
from src.dataset.loaders.base import BaseDatasetLoader
from src.preprocessing.index_mapper import IndexMapper
from src.preprocessing.temporal_processor import TemporalProcessor


class PTADiscLoader(BaseDatasetLoader):
    """Loader for the PTADisc dataset.

    Expected directory layout (after initial extraction)::

        raw_dir/
            ptadisc_train.csv
            ptadisc_test.csv

    Args:
        raw_dir:    Root of the PTADisc raw data directory.
        split:      ``"all"`` (default), ``"train"``, or ``"test"``.
        train_file: Filename for the training split CSV.
        test_file:  Filename for the test split CSV.
    """

    def __init__(
        self,
        raw_dir,
        split: str = "all",
        train_file: str = "ptadisc_train.csv",
        test_file: str = "ptadisc_test.csv",
    ):
        super().__init__(raw_dir, split)
        self._train_file = train_file
        self._test_file = test_file

    @property
    def name(self) -> str:
        return "ptadisc"

    def _csv_paths(self, for_all: bool = False):
        base = self.raw_dir
        train_path = base / self._train_file
        test_path = base / self._test_file
        paths = []
        if (for_all or self.split in ("all", "train")) and train_path.exists():
            paths.append(train_path)
        if (for_all or self.split in ("all", "test")) and test_path.exists():
            paths.append(test_path)
        if not paths:
            paths = sorted(base.glob("*.csv"))
        return paths

    def fit_mapper(self) -> IndexMapper:
        return TemporalProcessor.fit_mapper(self._csv_paths(for_all=True))

    def extract_to_dataframe(self, mapper: IndexMapper) -> pd.DataFrame:
        return TemporalProcessor.extract_to_dataframe(self._csv_paths(), mapper)
