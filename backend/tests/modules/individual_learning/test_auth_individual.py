from app.modules.auth.models import UserRole
from app.modules.auth.neo4j_repository import UPSERT_USER


def test_individual_role_exists() -> None:
    assert UserRole.INDIVIDUAL.value == "individual"


def test_user_graph_upsert_handles_individual_label() -> None:
    assert "REMOVE u:STUDENT:TEACHER:INDIVIDUAL" in UPSERT_USER
    assert "$role = 'individual'" in UPSERT_USER
    assert "SET u:INDIVIDUAL" in UPSERT_USER
