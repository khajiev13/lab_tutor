"""Flask application factory for the ARCD inference service.

Environment variables
---------------------
ARCD_CHECKPOINT_DIR
    Path to the arcd_train output directory containing ``best_model.pt``
    and ``vocab.json``.
    Default: ``<repo-root>/backend/checkpoints/roma_synth_v1``
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from flask import Flask

from arcd_agent.model_registry import ModelRegistry

logger = logging.getLogger(__name__)

# Module-level registry singleton — loaded once at import time so that
# every request reuses the same in-memory model.
_registry: ModelRegistry | None = None


def _default_checkpoint_dir() -> Path:
    """Resolve the default checkpoint directory relative to this file."""
    # backend/arcd_serving/app.py  →  backend/checkpoints/roma_synth_v1
    return Path(__file__).resolve().parent.parent / "checkpoints" / "roma_synth_v1"


def get_registry() -> ModelRegistry:
    global _registry
    if _registry is None:
        ckpt_dir = Path(
            os.environ.get("ARCD_CHECKPOINT_DIR", str(_default_checkpoint_dir()))
        )
        logger.info("ARCD serving: loading model from %s", ckpt_dir)
        _registry = ModelRegistry.from_dir(ckpt_dir)
        if _registry.is_available:
            logger.info(
                "ARCD serving: model ready  val_AUC=%.4f  version=%s",
                _registry.best_val_auc,
                _registry.model_version,
            )
        else:
            logger.warning(
                "ARCD serving: model NOT available — check ARCD_CHECKPOINT_DIR"
            )
    return _registry


def create_app() -> Flask:
    """Flask application factory."""
    logging.basicConfig(level=logging.INFO)

    app = Flask(__name__)

    # Pre-load the model eagerly so the first request isn't slow.
    with app.app_context():
        get_registry()

    from arcd_serving.routes import bp

    app.register_blueprint(bp)
    return app
