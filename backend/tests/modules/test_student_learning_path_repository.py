import logging
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


def test_record_resource_open_tracks_reading_relationship_and_timestamps():
    session = MagicMock()
    session.run.return_value.single.return_value = {"open_count": 1}

    neo4j_repository.record_resource_open(
        session,
        student_id=11,
        resource_type="reading",
        url="https://example.com/reading",
    )

    query = session.run.call_args.args[0]
    params = session.run.call_args.kwargs

    assert "MATCH (u:USER:STUDENT {id: $student_id})" in query
    assert "MATCH (r:READING_RESOURCE {url: $url})" in query
    assert "MERGE (u)-[rel:OPENED_READING]->(r)" in query
    assert "rel.open_count = coalesce(rel.open_count, 0) + 1" in query
    assert "rel.opened_at = coalesce(rel.opened_at, []) + [datetime()]" in query
    assert params["student_id"] == 11
    assert params["url"] == "https://example.com/reading"


def test_record_resource_open_tracks_video_relationship():
    session = MagicMock()
    session.run.return_value.single.return_value = {"open_count": 1}

    neo4j_repository.record_resource_open(
        session,
        student_id=11,
        resource_type="video",
        url="https://example.com/video",
    )

    query = session.run.call_args.args[0]

    assert "MATCH (r:VIDEO_RESOURCE {url: $url})" in query
    assert "MERGE (u)-[rel:OPENED_VIDEO]->(r)" in query


def test_record_resource_open_logs_and_noops_when_student_or_resource_missing(caplog):
    caplog.set_level(logging.INFO)
    session = MagicMock()
    session.run.return_value.single.return_value = None

    neo4j_repository.record_resource_open(
        session,
        student_id=11,
        resource_type="reading",
        url="https://example.com/missing",
    )

    assert "Skipping resource open tracking" in caplog.text


def test_get_accessible_reading_resource_scopes_lookup_to_student_course_path():
    session = MagicMock()
    session.run.return_value.single.return_value = {
        "resource": {
            "id": "reading-1",
            "title": "Batch Systems Guide",
            "url": "https://example.com/reading",
            "domain": "example.com",
            "snippet": "A short snippet.",
            "search_content": "A longer summary.",
            "reader_status": "ready",
            "reader_content_markdown": "# Batch Systems",
            "reader_error": "",
            "reader_extracted_at": "2026-04-15T00:00:00+00:00",
        }
    }

    result = neo4j_repository.get_accessible_reading_resource(
        session,
        student_id=11,
        course_id=2,
        resource_id="reading-1",
    )

    query = session.run.call_args.args[0]
    params = session.run.call_args.kwargs

    assert result["id"] == "reading-1"
    assert "SELECTED_SKILL" in query
    assert "HAS_READING" in query
    assert "READING_RESOURCE {id: $resource_id}" in query
    assert "reader_content_markdown" in query
    assert params["student_id"] == 11
    assert params["course_id"] == 2
    assert params["resource_id"] == "reading-1"


def test_persist_reading_reader_cache_updates_reader_fields():
    session = MagicMock()
    session.run.return_value.single.return_value = {"resource_id": "reading-1"}

    result = neo4j_repository.persist_reading_reader_cache(
        session,
        resource_id="reading-1",
        reader_status="failed",
        reader_content_markdown="",
        reader_error="This source timed out.",
        reader_extracted_at="2026-04-15T00:00:00+00:00",
    )

    query = session.run.call_args.args[0]
    params = session.run.call_args.kwargs

    assert result is True
    assert "rr.reader_status = $reader_status" in query
    assert "rr.reader_content_markdown = $reader_content_markdown" in query
    assert "rr.reader_error = CASE" in query
    assert "rr.reader_extracted_at = datetime($reader_extracted_at)" in query
    assert params["resource_id"] == "reading-1"
    assert params["reader_status"] == "failed"
    assert params["reader_error"] == "This source timed out."


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
                            "is_known": False,
                            "concepts": [],
                            "readings": [],
                            "videos": [],
                            "questions": [
                                {
                                    "id": "q-1",
                                    "text": "What is a batch?",
                                    "difficulty": "easy",
                                    "options": ["A", "B", "C", "D"],
                                }
                            ],
                        }
                    ],
                }
            },
            {
                "chapter": {
                    "title": "Streaming",
                    "chapter_index": 2,
                    "description": None,
                    "selected_skills": [],
                }
            },
        ],
        [
            {
                "chapter_index": 1,
                "easy_question_count": 1,
                "answered_count": 0,
                "correct_count": 0,
            }
        ],
    ]

    result = neo4j_repository.get_learning_path(session, student_id=11, course_id=2)

    assert result["course_title"] == "Data Systems"
    assert len(result["chapters"]) == 2
    assert result["total_selected_skills"] == 1
    assert result["skills_with_resources"] == 0
    assert result["chapters"][0]["quiz_status"] == "quiz_required"
    assert result["chapters"][0]["easy_question_count"] == 1
    assert result["chapters"][0]["answered_count"] == 0
    assert result["chapters"][0]["correct_count"] == 0
    assert result["chapters"][1]["title"] == "Streaming"
    assert result["chapters"][1]["selected_skills"] == []
    assert result["chapters"][0]["selected_skills"][0]["resource_status"] == "pending"
    assert result["chapters"][0]["selected_skills"][0]["is_known"] is False
    assert "answer" not in result["chapters"][0]["selected_skills"][0]["questions"][0]
    assert (
        "correct_option"
        not in result["chapters"][0]["selected_skills"][0]["questions"][0]
    )


def test_get_learning_path_projects_resource_ids_and_filters_pdf_readings():
    session = MagicMock()
    course_result = MagicMock()
    course_result.single.return_value = {"title": "Data Systems"}
    session.run.side_effect = [
        course_result,
        [],
        [],
    ]

    neo4j_repository.get_learning_path(session, student_id=11, course_id=2)

    query = session.run.call_args_list[1].args[0]

    assert "id: coalesce(rr.id, '')" in query
    assert "id: coalesce(vr.id, '')" in query
    assert "toLower(coalesce(rr.resource_type, '')) CONTAINS 'pdf'" in query
    assert "toLower(coalesce(rr.url, '')) CONTAINS '.pdf'" in query


def test_get_learning_path_applies_strict_sequence_quiz_status_math():
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
                    "selected_skills": [],
                }
            },
            {
                "chapter": {
                    "title": "Streaming",
                    "chapter_index": 2,
                    "description": None,
                    "selected_skills": [],
                }
            },
        ],
        [
            {
                "chapter_index": 1,
                "easy_question_count": 2,
                "answered_count": 2,
                "correct_count": 2,
            },
            {
                "chapter_index": 2,
                "easy_question_count": 3,
                "answered_count": 0,
                "correct_count": 0,
            },
        ],
    ]

    result = neo4j_repository.get_learning_path(session, student_id=11, course_id=2)

    assert result["chapters"][0]["quiz_status"] == "completed"
    assert result["chapters"][1]["quiz_status"] == "quiz_required"
    assert result["chapters"][0]["answered_count"] == 2
    assert result["chapters"][0]["correct_count"] == 2
    assert result["chapters"][1]["easy_question_count"] == 3


def test_get_learning_path_keeps_next_chapter_locked_until_prior_is_fully_correct():
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
                    "selected_skills": [],
                }
            },
            {
                "chapter": {
                    "title": "Streaming",
                    "chapter_index": 2,
                    "description": None,
                    "selected_skills": [],
                }
            },
        ],
        [
            {
                "chapter_index": 1,
                "easy_question_count": 2,
                "answered_count": 1,
                "correct_count": 1,
            },
            {
                "chapter_index": 2,
                "easy_question_count": 3,
                "answered_count": 0,
                "correct_count": 0,
            },
        ],
    ]

    result = neo4j_repository.get_learning_path(session, student_id=11, course_id=2)

    assert result["chapters"][0]["quiz_status"] == "learning"
    assert result["chapters"][1]["quiz_status"] == "locked"


def test_get_chapter_easy_questions_omits_correct_answer_and_collects_previous_answers():
    session = MagicMock()
    session.run.return_value = [
        {
            "chapter_title": "Foundations",
            "id": "q-1",
            "skill_name": "Batch Processing",
            "text": "What is a batch job?",
            "options": ["A", "B", "C", "D"],
            "previous_answer": {
                "selected_option": "B",
                "answered_right": True,
                "answered_at": "2026-04-14T08:00:00Z",
            },
        }
    ]

    result = neo4j_repository.get_chapter_easy_questions(
        session,
        student_id=11,
        course_id=2,
        chapter_index=1,
    )

    assert result["chapter_title"] == "Foundations"
    assert result["questions"] == [
        {
            "id": "q-1",
            "skill_name": "Batch Processing",
            "text": "What is a batch job?",
            "options": ["A", "B", "C", "D"],
        }
    ]
    assert result["previous_answers"]["q-1"]["selected_option"] == "B"


def test_submit_chapter_answers_merges_answered_relationship():
    session = MagicMock()
    session.run.return_value = [
        {
            "question_id": "q-1",
            "skill_name": "Batch Processing",
            "selected_option": "B",
            "answered_right": True,
            "correct_option": "B",
        }
    ]

    result = neo4j_repository.submit_chapter_answers(
        session,
        student_id=11,
        course_id=2,
        chapter_index=1,
        submissions=[{"question_id": "q-1", "selected_option": "B"}],
    )

    query = session.run.call_args.args[0]

    assert result[0]["correct_option"] == "B"
    assert "MERGE (u)-[a:ANSWERED]->(q)" in query
    assert "WHEN coalesce(a.answered_right, false) = true THEN true" in query
    assert "WHEN coalesce(a.answered_right, false) = true AND correct = false" in query


def test_get_chapter_quiz_progress_returns_counts_per_selected_chapter():
    session = MagicMock()
    session.run.return_value = [
        {
            "chapter_index": 1,
            "easy_question_count": 2,
            "answered_count": 1,
            "correct_count": 1,
        },
        {
            "chapter_index": 2,
            "easy_question_count": 3,
            "answered_count": 0,
            "correct_count": 0,
        },
    ]

    result = neo4j_repository.get_chapter_quiz_progress(
        session,
        student_id=11,
        course_id=2,
    )

    assert result == [
        {
            "chapter_index": 1,
            "easy_question_count": 2,
            "answered_count": 1,
            "correct_count": 1,
        },
        {
            "chapter_index": 2,
            "easy_question_count": 3,
            "answered_count": 0,
            "correct_count": 0,
        },
    ]


def test_resolve_quiz_statuses_skips_zero_question_chapters():
    statuses = neo4j_repository.resolve_quiz_statuses(
        [
            {
                "chapter_index": 1,
                "easy_question_count": 1,
                "answered_count": 1,
                "correct_count": 1,
            },
            {
                "chapter_index": 2,
                "easy_question_count": 0,
                "answered_count": 0,
                "correct_count": 0,
            },
            {
                "chapter_index": 3,
                "easy_question_count": 1,
                "answered_count": 0,
                "correct_count": 0,
            },
        ]
    )

    assert statuses == {
        1: "completed",
        2: "learning",
        3: "quiz_required",
    }
