"""CLI entry-point: ``python -m arcd_serving.run``

Usage
-----
    cd backend
    ARCD_CHECKPOINT_DIR=checkpoints/roma_synth_v6_2048 \\
        uv run python -m arcd_serving.run --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import argparse
import sys

from arcd_serving.app import create_app


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ARCD Flask inference service",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind address")
    parser.add_argument("--port", type=int, default=8000, help="Listen port")
    parser.add_argument(
        "--debug", action="store_true", help="Enable Flask debug mode (dev only)"
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    app = create_app()
    print(
        f"ARCD serving: starting on http://{args.host}:{args.port}  "
        f"(debug={args.debug})",
        file=sys.stderr,
    )
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
