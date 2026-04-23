"""ARCD Flask inference service.

Entry-point: ``python -m app.modules.arcd_serving.run``

The app is configured via environment variables (see :py:mod:`app.modules.arcd_serving.app`).
"""

from app.modules.arcd_serving.app import create_app

__all__ = ["create_app"]
