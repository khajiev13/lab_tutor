"""
src/dataset — Unified dataset module for ARCD.

Provides:
    IndexMapper           — bidirectional ID ↔ index mapping
    TemporalProcessor     — CSV → DataFrame preprocessor
    loaders               — per-dataset loader interfaces (XES3G5M, Junyi, EdNet)
"""

from src.dataset.index_mapper import IndexMapper
from src.dataset.loaders import (
    BaseDatasetLoader,
    EdNetLoader,
    JunyiLoader,
    XES3G5MLoader,
    get_loader,
)
from src.dataset.temporal_processor import TemporalProcessor

__all__ = [
    "IndexMapper",
    "TemporalProcessor",
    "BaseDatasetLoader",
    "XES3G5MLoader",
    "JunyiLoader",
    "EdNetLoader",
    "get_loader",
]
