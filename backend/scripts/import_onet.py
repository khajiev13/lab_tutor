"""Administrative O*NET release download, validation and atomic SQL import."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.occupation_reference.importer import (  # noqa: E402
    download_release,
    parse_release,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", default="31.0")
    parser.add_argument("--cache-dir", type=Path, default=Path("/app/data/onet"))
    parser.add_argument("--from-dir", type=Path)
    parser.add_argument(
        "--activate",
        action="store_true",
        help="Make the complete imported release active",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Parse files without initializing SQL",
    )
    args = parser.parse_args(argv)
    try:
        directory = args.from_dir
        if directory is None:
            with httpx.Client() as client:
                directory = download_release(args.release, args.cache_dir, client)
        parsed = parse_release(directory, args.release)
    except (OSError, ValueError, httpx.HTTPError) as exc:
        print(f"O*NET validation failed: {exc}", file=sys.stderr)
        return 1
    summary = {
        "version": parsed.version,
        "occupations": len(parsed.occupations),
        "evidence": len(parsed.evidence),
        "files": parsed.manifest["files"],
        "validated_only": args.validate_only,
        "metric_statuses": dict(
            Counter(
                metric["status"]
                for item in parsed.evidence
                for metric in item.ratings.values()
            )
        ),
        "families": dict(Counter(item.family for item in parsed.evidence)),
        "software_flags": dict(
            Counter(
                key
                for item in parsed.evidence
                if item.family == "software"
                for key, value in item.flags.items()
                if value is True
            )
        ),
    }
    if not args.validate_only:
        try:
            # main registers every model before create_all, including User/Course
            # relationships and FK targets. No DB modules load in validate-only.
            import main as application  # noqa: F401
            from app.core.database import Base, SessionLocal, engine
            from app.modules.occupation_reference.repository import (
                OccupationReferenceRepository,
            )

            Base.metadata.create_all(bind=engine)
            with SessionLocal() as session:
                row = OccupationReferenceRepository(session).import_release(
                    parsed, activate=args.activate
                )
                summary["active"] = row.active
        except Exception as exc:
            # SQL driver exceptions can contain connection details; omit them.
            print(f"O*NET SQL import failed ({type(exc).__name__})", file=sys.stderr)
            return 1
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
