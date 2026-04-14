from unittest.mock import MagicMock

from app.modules.student_learning_path import neo4j_repository


def test_get_student_skill_banks_returns_nested_books():
    session = MagicMock()
    neo4j_repository.CourseGraphRepository.get_skill_selection_range = (  # type: ignore[method-assign]
        lambda self, *, course_id: {
            "min_skills": 20,
            "max_skills": 35,
            "is_default": True,
        }
    )
    session.run.side_effect = [
        [{"name": "Batch Processing", "source": "book"}],
        [{"url": "https://jobs.example/backend"}],
        [
            {"skill_name": "Batch Processing", "student_count": 3},
            {"skill_name": "Kafka", "student_count": 1},
        ],
        [
            {
                "prerequisite_name": "Addition",
                "dependent_name": "Multiplication",
                "confidence": "high",
                "reasoning": "Addition comes first.",
            }
        ],
        [
            {
                "book": {
                    "book_id": "book-1",
                    "title": "Designing Data Systems",
                    "authors": "Alex Example",
                    "chapters": [
                        {
                            "chapter_id": "chapter-1",
                            "title": "Distributed Foundations",
                            "chapter_index": 1,
                            "skills": [
                                {
                                    "name": "Batch Processing",
                                    "description": "Process large datasets reliably.",
                                }
                            ],
                        }
                    ],
                }
            },
            {
                "book": {
                    "book_id": "book-2",
                    "title": "Streaming Data",
                    "authors": "Jamie Example",
                    "chapters": [
                        {
                            "chapter_id": "chapter-2",
                            "title": "Event Streams",
                            "chapter_index": 2,
                            "skills": [],
                        }
                    ],
                }
            },
        ],
        [
            {
                "job_posting": {
                    "url": "https://jobs.example/backend",
                    "title": "Backend Engineer",
                    "company": "Acme",
                    "site": "LinkedIn",
                    "search_term": "backend engineer",
                    "skills": [
                        {
                            "name": "Kafka",
                            "description": "Stream events across services.",
                            "category": "data_processing",
                        }
                    ],
                }
            }
        ],
    ]

    result = neo4j_repository.get_student_skill_banks(
        session, student_id=11, course_id=2
    )

    assert len(result.book_skill_banks) == 2
    assert result.book_skill_banks[0].title == "Designing Data Systems"
    assert result.book_skill_banks[0].chapters[0].title == "Distributed Foundations"
    assert result.book_skill_banks[0].chapters[0].skills[0].is_selected is True
    assert result.book_skill_banks[0].chapters[0].skills[0].peer_count == 3
    assert result.market_skill_bank[0].is_interested is True
    assert result.market_skill_bank[0].skills[0].category == "data_processing"
    assert result.selection_range.min_skills == 20
    assert result.prerequisite_edges[0].prerequisite_name == "Addition"


def test_get_student_skill_banks_handles_missing_book_and_chapter_titles():
    session = MagicMock()
    neo4j_repository.CourseGraphRepository.get_skill_selection_range = (  # type: ignore[method-assign]
        lambda self, *, course_id: {
            "min_skills": 20,
            "max_skills": 35,
            "is_default": True,
        }
    )
    session.run.side_effect = [
        [],
        [],
        [],
        [],
        [
            {
                "book": {
                    "book_id": "book-1",
                    "title": None,
                    "authors": None,
                    "chapters": [
                        {
                            "chapter_id": "chapter-1",
                            "title": None,
                            "chapter_index": 3,
                            "skills": [],
                        }
                    ],
                }
            }
        ],
        [],
    ]

    result = neo4j_repository.get_student_skill_banks(
        session, student_id=11, course_id=2
    )

    assert result.book_skill_banks[0].title == "Untitled book"
    assert result.book_skill_banks[0].chapters[0].title == "Chapter 3"


def test_get_student_skill_banks_keeps_legacy_market_skills_visible():
    session = MagicMock()
    neo4j_repository.CourseGraphRepository.get_skill_selection_range = (  # type: ignore[method-assign]
        lambda self, *, course_id: {
            "min_skills": 20,
            "max_skills": 35,
            "is_default": True,
        }
    )
    session.run.side_effect = [
        [],
        [],
        [],
        [],
        [],
        [
            {
                "job_posting": {
                    "url": "https://jobs.example/backend",
                    "title": "Backend Engineer",
                    "company": "Acme",
                    "site": "LinkedIn",
                    "search_term": "backend engineer",
                    "skills": [
                        {
                            "name": "Kafka",
                            "description": "Stream events across services.",
                            "category": "data_processing",
                        }
                    ],
                }
            }
        ],
    ]

    result = neo4j_repository.get_student_skill_banks(
        session, student_id=11, course_id=2
    )

    assert len(result.market_skill_bank) == 1
    assert result.market_skill_bank[0].title == "Backend Engineer"
    assert result.market_skill_bank[0].skills[0].name == "Kafka"


def test_select_skills_scopes_book_selection_to_course():
    session = MagicMock()
    session.run.return_value.single.return_value = {"written": 1}

    result = neo4j_repository.select_skills(
        session,
        student_id=11,
        course_id=2,
        skill_names=["Batch Processing"],
        source="book",
    )

    query = session.run.call_args.args[0]
    params = session.run.call_args.kwargs

    assert result == 1
    assert "CANDIDATE_BOOK" in query
    assert "BOOK_SKILL" in query
    assert params["course_id"] == 2


def test_select_job_postings_scopes_market_skills_to_course():
    session = MagicMock()
    session.run.return_value.single.return_value = {"postings_linked": 1}

    result = neo4j_repository.select_job_postings(
        session,
        student_id=11,
        course_id=2,
        posting_urls=["https://jobs.example/backend"],
    )

    query = session.run.call_args.args[0]
    params = session.run.call_args.kwargs

    assert result == 1
    assert "MARKET_SKILL" in query
    assert "ms.course_id = $course_id OR ms.course_id IS NULL" in query
    assert "WITH u, jp, skill_name, head(collect(ms)) AS ms" in query
    assert params["course_id"] == 2


def test_get_learning_path_marks_skills_pending_without_resources():
    session = MagicMock()
    course_result = MagicMock()
    course_result.single.return_value = {"title": "Data Systems"}
    session.run.side_effect = [
        course_result,
        [
            {
                "chapter": {
                    "title": "Foundations",
                    "chapter_index": 1,
                    "description": None,
                    "selected_skills": [
                        {
                            "name": "Batch Processing",
                            "description": "Process large datasets reliably.",
                            "source": "book",
                            "skill_type": "book",
                            "concepts": [],
                            "readings": [],
                            "videos": [],
                            "questions": [],
                        }
                    ],
                }
            }
        ],
    ]

    result = neo4j_repository.get_learning_path(session, student_id=11, course_id=2)

    assert result["course_title"] == "Data Systems"
    assert result["total_selected_skills"] == 1
    assert result["skills_with_resources"] == 0
    assert result["chapters"][0]["selected_skills"][0]["resource_status"] == "pending"
