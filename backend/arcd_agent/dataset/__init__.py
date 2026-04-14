"""
src/dataset — Unified dataset module for ARCD.

Provides:
    IndexMapper           — bidirectional ID ↔ index mapping
    TemporalProcessor     — CSV → DataFrame preprocessor (XES3G5M format)
    loaders               — per-dataset loader interfaces

Re-exports everything from src.preprocessing for backward compatibility.
"""

from src.dataset.loaders import (
    BaseDatasetLoader,
    EdNetLoader,
    JunyiLoader,
    PTADiscLoader,
    XES3G5MLoader,
    get_loader,
)
from src.preprocessing.index_mapper import IndexMapper
from src.preprocessing.temporal_processor import TemporalProcessor

__all__ = [
    "IndexMapper",
    "TemporalProcessor",
    "BaseDatasetLoader",
    "XES3G5MLoader",
    "JunyiLoader",
    "PTADiscLoader",
    "EdNetLoader",
    "get_loader",
]
