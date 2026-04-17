"""
src/dataset/loaders — Per-dataset loader interfaces.

Each loader knows how to:
    1. locate the raw dataset files
    2. build an IndexMapper over all splits
    3. produce a processed DataFrame for model training

All loaders share a common BaseDatasetLoader interface so that training
scripts can swap datasets without changing control flow.

Usage::

    from app.modules.arcd.dataset.loaders import get_loader

    loader = get_loader("xes3g5m", raw_dir=Path("data/datasets/xes3g5m"))
    mapper = loader.fit_mapper()
    df     = loader.extract_to_dataframe(mapper)
"""

from app.modules.arcd.dataset.loaders.base import BaseDatasetLoader
from app.modules.arcd.dataset.loaders.ednet import EdNetLoader
from app.modules.arcd.dataset.loaders.junyi import JunyiLoader
from app.modules.arcd.dataset.loaders.ptadisc import PTADiscLoader
from app.modules.arcd.dataset.loaders.xes3g5m import XES3G5MLoader

_REGISTRY: dict[str, type[BaseDatasetLoader]] = {
    "xes3g5m": XES3G5MLoader,
    "junyi": JunyiLoader,
    "ptadisc": PTADiscLoader,
    "ednet": EdNetLoader,
}


def get_loader(dataset: str, raw_dir, **kwargs) -> "BaseDatasetLoader":
    """Instantiate the appropriate dataset loader.

    Args:
        dataset: Dataset name — one of ``xes3g5m``, ``junyi``, ``ptadisc``, ``ednet``.
        raw_dir: Path to the raw dataset directory.
        **kwargs: Forwarded to the loader constructor.

    Returns:
        Configured ``BaseDatasetLoader`` instance.

    Raises:
        ValueError: If ``dataset`` is not recognised.
    """
    key = dataset.lower().strip()
    if key not in _REGISTRY:
        raise ValueError(f"Unknown dataset {dataset!r}. Available: {sorted(_REGISTRY)}")
    return _REGISTRY[key](raw_dir=raw_dir, **kwargs)


__all__ = [
    "BaseDatasetLoader",
    "XES3G5MLoader",
    "JunyiLoader",
    "PTADiscLoader",
    "EdNetLoader",
    "get_loader",
]
