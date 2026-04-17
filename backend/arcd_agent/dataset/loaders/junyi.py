"""
src/dataset/loaders/junyi.py — Junyi Academy dataset loader.

Junyi uses a similar 5-column CSV format to XES3G5M.
"""

from __future__ import annotations

import pandas as pd
from src.dataset.loaders.base import BaseDatasetLoader
from src.preprocessing.index_mapper import IndexMapper
from src.preprocessing.temporal_processor import TemporalProcessor


class JunyiLoader(BaseDatasetLoader):
    """Loader for the Junyi Academy knowledge-tracing dataset.

    Expected directory layout::

        raw_dir/
            train_sequences.csv   (or train_valid_sequences_quelevel.csv)
            test_sequences.csv

    If the exact filenames differ from the defaults you can pass
    ``train_file`` / ``test_file`` to the constructor.

    Args:
        raw_dir:    Root of the Junyi raw data directory.
        split:      ``"all"`` (default), ``"train"``, or ``"test"``.
        train_file: Filename for the training split CSV.
        test_file:  Filename for the test split CSV.
    """

    def __init__(
        self,
        raw_dir,
        split: str = "all",
        train_file: str = "train_valid_sequences_quelevel.csv",
        test_file: str = "test_sequences_quelevel.csv",
    ):
        super().__init__(raw_dir, split)
        self._train_file = train_file
        self._test_file = test_file

    @property
    def name(self) -> str:
        return "junyi"

    def _csv_paths(self, for_all: bool = False):
        base = self.raw_dir
        train_path = base / self._train_file
        test_path = base / self._test_file
        paths = []
        if (for_all or self.split in ("all", "train", "valid")) and train_path.exists():
            paths.append(train_path)
        if (for_all or self.split in ("all", "test")) and test_path.exists():
            paths.append(test_path)
        if not paths:
            # Fallback: collect any CSV in the directory
            paths = sorted(base.glob("*.csv"))
        return paths

    def fit_mapper(self) -> IndexMapper:
        return TemporalProcessor.fit_mapper(self._csv_paths(for_all=True))

    def extract_to_dataframe(self, mapper: IndexMapper) -> pd.DataFrame:
        return TemporalProcessor.extract_to_dataframe(self._csv_paths(), mapper)
