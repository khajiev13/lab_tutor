"""
src/dataset — Unified dataset module for ARCD.

Provides:
    IndexMapper           — bidirectional ID ↔ index mapping
    TemporalProcessor     — CSV → DataFrame preprocessor (XES3G5M format)
    loaders               — per-dataset loader interfaces

Re-exports everything from app.modules.arcd.preprocessing for backward compatibility.
"""

from app.modules.arcd.dataset.loaders import (
    BaseDatasetLoader,
    EdNetLoader,
    JunyiLoader,
    PTADiscLoader,
    XES3G5MLoader,
    get_loader,
)
from app.modules.arcd.preprocessing.index_mapper import IndexMapper
from app.modules.arcd.preprocessing.temporal_processor import TemporalProcessor

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
