from pathlib import Path

import pytest


@pytest.fixture
def fixture_dir():
    return Path(__file__).parents[2] / "fixtures" / "onet" / "31.0"


@pytest.fixture
def parsed_release(fixture_dir):
    from app.modules.occupation_reference.importer import parse_release

    return parse_release(fixture_dir, "31.0")


@pytest.fixture
def course(client, teacher_auth_headers):
    response = client.post(
        "/courses", json={"title": "O*NET catalog course"}, headers=teacher_auth_headers
    )
    assert response.status_code == 201
    return response.json()
