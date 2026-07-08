from app.modules.individual_learning.service import IndividualLearningService


def test_get_profile_returns_default_onboarding_state() -> None:
    service = IndividualLearningService(db=None, neo4j_driver=None)
    profile = service.get_profile(user_id=42)

    assert profile.user_id == 42
    assert profile.onboarding_status == "needs_cv"
    assert profile.target_titles == []
