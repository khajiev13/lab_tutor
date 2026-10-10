import json
import os
import subprocess
import sys
from pathlib import Path


def test_validate_only_runs_offline_without_sql_initialization(fixture_dir):
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[3] / "scripts" / "import_onet.py"),
            "--release",
            "31.0",
            "--from-dir",
            str(fixture_dir),
            "--validate-only",
        ],
        env={**os.environ, "LAB_TUTOR_DATABASE_URL": "invalid-database-url"},
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["validated_only"] is True
    assert summary["evidence"] == 4
    assert summary["metric_statuses"] == {
        "reported": 1,
        "missing": 1,
        "suppressed": 1,
        "not_relevant": 1,
    }
    assert "active" not in summary
