from unittest.mock import MagicMock

from app.modules.courses.curriculum_neo4j_repository import (
    CurriculumNeo4jRepository,
)


def test_get_market_skill_bank_queries_course_chapter_mappings():
    session = MagicMock()
    session.run.return_value = []
    repository = CurriculumNeo4jRepository(session)

    repository.get_market_skill_bank(course_id=2)

    query = session.run.call_args.args[0]
    params = session.run.call_args.kwargs

    assert "HAS_COURSE_CHAPTER" in query
    assert "MAPPED_TO" in query
    assert "CANDIDATE_BOOK" not in query
    assert params == {"course_id": 2}
