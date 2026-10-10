from copy import deepcopy
from dataclasses import replace

import pytest
from sqlalchemy.exc import IntegrityError


def test_import_is_immutable_idempotent_and_all_flags_load(db_session, parsed_release):
    from app.modules.occupation_reference.repository import (
        OccupationReferenceRepository,
        ReleaseConflictError,
    )

    repo = OccupationReferenceRepository(db_session)
    repo.import_release(parsed_release, activate=True)
    changed_timestamp = deepcopy(parsed_release)
    changed_timestamp.manifest["retrieved_at"] = "later"
    repo.import_release(changed_timestamp, activate=True)
    assert repo.count_evidence("31.0") == 4
    assert repo.active_release().version == "31.0"
    evidence = repo.load_occupation_evidence("31.0", ["15-2051.00"])
    assert len(evidence) == 4
    assert (
        next(item for item in evidence if item.family == "transferable").ratings["IM"][
            "status"
        ]
        == "suppressed"
    )
    changed = deepcopy(parsed_release)
    changed.manifest["files"]["essential_skills.csv"]["sha256"] = "0" * 64
    with pytest.raises(ReleaseConflictError):
        repo.import_release(changed, activate=True)
    assert repo.count_evidence("31.0") == 4


def test_failed_later_batch_rolls_back_and_keeps_old_release(
    db_session, parsed_release, fixture_dir, monkeypatch
):
    from app.modules.occupation_reference.repository import (
        OccupationReferenceRepository,
    )

    repo = OccupationReferenceRepository(db_session)
    repo.import_release(parsed_release, activate=True)
    monkeypatch.setattr("app.modules.occupation_reference.repository.BATCH_SIZE", 2)
    from app.modules.occupation_reference.importer import parse_release

    next_release = parse_release(fixture_dir, "32.0")
    invalid = replace(
        next_release,
        evidence=[
            *next_release.evidence,
            replace(
                next_release.evidence[0],
                id="a5a30b11-95a5-473d-a8c9-fef309a7a54a",
                soc_code="99-9999.00",
            ),
        ],
    )
    with pytest.raises(IntegrityError):
        repo.import_release(invalid, activate=True)
    assert repo.active_release().version == "31.0"
    assert [release.version for release in repo.list_releases()] == ["31.0"]
    assert repo.count_evidence("32.0") == 0


def test_concurrent_activation_keeps_exactly_one_active_release(
    db_session, parsed_release, fixture_dir
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from sqlalchemy.orm import Session

    from app.modules.occupation_reference.repository import (
        OccupationReferenceRepository,
    )

    barrier = Barrier(2)
    engine = db_session.get_bind()

    def activate(version):
        with Session(engine) as session:
            barrier.wait(timeout=10)
            from app.modules.occupation_reference.importer import parse_release

            OccupationReferenceRepository(session).import_release(
                parse_release(fixture_dir, version), activate=True
            )

    with ThreadPoolExecutor(max_workers=2) as workers:
        tasks = [workers.submit(activate, version) for version in ("31.0", "32.0")]
        for task in tasks:
            task.result(timeout=20)
    db_session.expire_all()
    repo = OccupationReferenceRepository(db_session)
    assert sum(release.active for release in repo.list_releases()) == 1
    assert repo.count_evidence("31.0") == repo.count_evidence("32.0") == 4
