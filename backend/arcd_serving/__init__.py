"""ARCD Flask inference service.

Entry-point: ``python -m arcd_serving.run``

The app is configured via environment variables (see :py:mod:`arcd_serving.app`).
"""
from arcd_serving.app import create_app

__all__ = ["create_app"]
