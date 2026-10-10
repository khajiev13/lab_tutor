import csv
import shutil

import pytest


def modify_file(directory, filename, mutate):
    path = directory / filename
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.reader(stream))
    mutate(rows)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        csv.writer(stream).writerows(rows)


def test_ratings_preserve_missing_suppressed_and_not_relevant(parsed_release):
    by_family = {item.family: item for item in parsed_release.evidence}
    essential = by_family["essential"]
    assert essential.ratings["IM"]["value"] == 4.2
    assert essential.ratings["IM"]["minimum"] == 1
    assert essential.ratings["IM"]["maximum"] == 5
    assert essential.ratings["LV"]["value"] is None
    assert essential.ratings["LV"]["status"] == "missing"
    assert essential.ratings["LV"]["maximum"] == 7
    transferable = by_family["transferable"]
    assert transferable.ratings["IM"]["status"] == "suppressed"
    assert transferable.ratings["IM"]["value"] == 2.4
    assert transferable.ratings["IM"]["quality"]["Standard Error"] == "0.3"
    assert transferable.ratings["LV"]["status"] == "not_relevant"
    assert transferable.ratings["LV"]["value"] == 0
    assert essential.source_rows[0]["Date"] == "08/2026"


def test_software_identity_and_flags_preserve_exact_examples(parsed_release):
    from app.modules.occupation_reference.importer import source_record_id

    items = [item for item in parsed_release.evidence if item.family == "software"]
    assert len({item.id for item in items}) == 2
    postgres = next(item for item in items if item.workplace_example == "PostgreSQL")
    assert postgres.ratings == {}
    assert postgres.flags == {"Hot Technology": True, "In Demand": False}
    assert postgres.id == source_record_id(
        "31.0", "15-2051.00", "software", "2.E.6.f", "PostgreSQL"
    )
    assert postgres.id != source_record_id(
        "31.0", "15-2051.00", "software", "2.E.6.f", "postgresql"
    )
    assert parsed_release.occupations[0].alternate_titles == ["Analytics Engineer"]


@pytest.mark.parametrize(
    "filename,mutate",
    [
        ("essential_skills.csv", lambda rows: rows[0].__setitem__(6, "Unknown Value")),
        ("essential_skills.csv", lambda rows: rows[1].__setitem__(6, "nan")),
        ("essential_skills.csv", lambda rows: rows[1].__setitem__(6, "6")),
        ("essential_skills.csv", lambda rows: rows[1].__setitem__(4, "XX")),
        ("essential_skills.csv", lambda rows: rows[1].__setitem__(0, "99-9999.00")),
        ("essential_skills.csv", lambda rows: rows[1].__setitem__(2, "unknown")),
        ("essential_skills.csv", lambda rows: rows[1].__setitem__(11, "yes")),
        ("essential_skills.csv", lambda rows: rows[1].__setitem__(13, "2026-99")),
        ("essential_skills.csv", lambda rows: rows.append(rows[1][:])),
        ("software_skills.csv", lambda rows: rows.append(rows[1][:])),
        ("occupation_data.csv", lambda rows: rows[1].__setitem__(0, "15-2051")),
        ("occupation_data.csv", lambda rows: rows[1].__setitem__(1, "")),
    ],
)
def test_invalid_source_rows_fail_closed(fixture_dir, tmp_path, filename, mutate):
    from app.modules.occupation_reference.importer import parse_release

    shutil.copytree(fixture_dir, tmp_path / "input")
    modify_file(tmp_path / "input", filename, mutate)
    with pytest.raises(ValueError):
        parse_release(tmp_path / "input", "31.0")


def test_required_file_and_invalid_encoding_are_rejected(fixture_dir, tmp_path):
    from app.modules.occupation_reference.importer import parse_release

    shutil.copytree(fixture_dir, tmp_path / "input")
    target = tmp_path / "input" / "software_skills.csv"
    target.unlink()
    with pytest.raises(ValueError):
        parse_release(tmp_path / "input", "31.0")
    target.write_bytes(b"\xff")
    with pytest.raises(ValueError):
        parse_release(tmp_path / "input", "31.0")


def test_manifest_records_all_original_checksums_urls_and_rows(parsed_release):
    files = parsed_release.manifest["files"]
    assert len(files) == 7
    assert files["essential_skills.csv"]["row_count"] == 2
    assert (
        files["essential_skills.csv"]["url"]
        == "https://www.onetcenter.org/dl_files/database/db_31_0_csv/essential_skills.csv"
    )
    assert len(files["essential_skills.csv"]["sha256"]) == 64
    assert "CC BY 4.0" in parsed_release.attribution
