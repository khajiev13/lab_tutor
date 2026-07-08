from app.modules.auth.models import UserRole
from app.modules.individual_learning import routes


def test_individual_learning_router_prefix() -> None:
    assert routes.router.prefix == "/individual-learning"


def test_individual_learning_uses_individual_role() -> None:
    assert routes.INDIVIDUAL_ROLE == UserRole.INDIVIDUAL
