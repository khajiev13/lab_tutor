"""
src/dataset/loaders/base.py — Abstract base class for all dataset loaders.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd


class BaseDatasetLoader(ABC):
    """Abstract dataset loader interface.

    Subclasses must implement ``fit_mapper`` and ``extract_to_dataframe``.
    Optionally override ``name`` and ``splits``.

    Attributes:
        raw_dir:  Root directory containing the raw dataset files.
        split:    Which split(s) to load — ``"train"``, ``"valid"``, ``"test"``, or ``"all"``.
    """

    def __init__(self, raw_dir: Path | str, split: str = "all"):
        self.raw_dir = Path(raw_dir)
        self.split = split

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable dataset name."""

    @abstractmethod
    def fit_mapper(self):
        """Scan raw files and return a fitted :class:`~src.dataset.IndexMapper`.

        Returns:
            :class:`~src.dataset.IndexMapper` fitted on all unique IDs.
        """

    @abstractmethod
    def extract_to_dataframe(self, mapper) -> pd.DataFrame:
        """Build the processed interaction DataFrame.

        Args:
            mapper: A fitted :class:`~src.dataset.IndexMapper`.

        Returns:
            DataFrame with columns:
            ``student_idx``, ``question_idx``, ``skill_idx``, ``correct``, ``t_sec``.
        """

    def load(self) -> tuple:
        """Convenience method: fit + extract in one call.

        Returns:
            Tuple of ``(mapper, dataframe)``.
        """
        mapper = self.fit_mapper()
        df = self.extract_to_dataframe(mapper)
        return mapper, df

    def __repr__(self) -> str:
        return f"{type(self).__name__}(raw_dir={self.raw_dir!r}, split={self.split!r})"
