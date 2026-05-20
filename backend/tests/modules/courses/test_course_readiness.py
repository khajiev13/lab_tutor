from app.modules.courses.models import (
    Course,
    CourseMarketGateStatus,
    CoursePublicationStatus,
)
from app.modules.curricularalignmentarchitect.models import (
    BookSelectionSession,
    SessionStatus,
)
from app.modules.curricularalignmentarchitect.skill_prerequisites.review_models import (
    PrerequisiteReview,
)
from app.modules.curricularalignmentarchitect.skill_prerequisites.schemas import (
    PrerequisiteReviewStatus,
)


def _create_course(client, teacher_auth_headers, title="Readiness Course") -> int:
    response = client.post(
        "/courses",
        json={"title": title, "description": "Course used by readiness tests"},
        headers=teacher_auth_headers,
    )
    assert response.status_code == 201
    return int(response.json()["id"])


def _publish_course_directly(db_session, course_id: int) -> None:
    course = db_session.get(Course, course_id)
    assert course is not None
    course.publication_status = CoursePublicationStatus.PUBLISHED
    db_session.add(course)
    db_session.commit()


def _mark_book_gate_complete(db_session, course_id: int) -> None:
    db_session.add(
        BookSelectionSession(
            course_id=course_id,
            thread_id=f"book-session-{course_id}",
            status=SessionStatus.COMPLETED,
        )
    )
    db_session.commit()


def _mark_market_gate_complete(db_session, course_id: int) -> None:
    course = db_session.get(Course, course_id)
    assert course is not None
    course.market_gate_status = CourseMarketGateStatus.COMPLETED
    db_session.add(course)
    db_session.commit()


def _mark_prerequisites_approved(db_session, course_id: int) -> None:
    db_session.add(
        PrerequisiteReview(
            course_id=course_id,
            review_status=PrerequisiteReviewStatus.APPROVED,
            draft_edges=[],
            isolated_skills_viewed=True,
        )
    )
    db_session.commit()


def test_new_course_is_draft_and_hidden_from_student_catalog(
    client,
    teacher_auth_headers,
):
    course_id = _create_course(client, teacher_auth_headers)

    teacher_response = client.get("/courses/my", headers=teacher_auth_headers)
    assert teacher_response.status_code == 200
    teacher_course = next(c for c in teacher_response.json() if c["id"] == course_id)
    assert teacher_course["publication_status"] == "draft"

    public_response = client.get("/courses")
    assert public_response.status_code == 200
    assert all(c["id"] != course_id for c in public_response.json())


def test_student_join_rejects_draft_course(
    client,
    teacher_auth_headers,
    student_auth_headers,
):
    course_id = _create_course(client, teacher_auth_headers)

    response = client.post(f"/courses/{course_id}/join", headers=student_auth_headers)

    assert response.status_code == 403
    assert response.json()["detail"] == "Course is not available for enrollment"


def test_student_catalog_and_join_allow_published_course(
    client,
    db_session,
    teacher_auth_headers,
    student_auth_headers,
):
    course_id = _create_course(client, teacher_auth_headers, title="Published Course")
    _mark_book_gate_complete(db_session, course_id)
    _mark_market_gate_complete(db_session, course_id)
    _mark_prerequisites_approved(db_session, course_id)
    _publish_course_directly(db_session, course_id)

    public_response = client.get("/courses")
    assert public_response.status_code == 200
    assert any(c["id"] == course_id for c in public_response.json())

    join_response = client.post(
        f"/courses/{course_id}/join",
        headers=student_auth_headers,
    )
    assert join_response.status_code == 201
    assert join_response.json()["course_id"] == course_id


def test_readiness_returns_next_action_and_blockers(
    client,
    teacher_auth_headers,
):
    course_id = _create_course(client, teacher_auth_headers, title="Blocked Course")

    response = client.get(
        f"/courses/{course_id}/readiness",
        headers=teacher_auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["can_publish"] is False
    assert payload["next_action"]["id"] == "book"
    assert "Complete the book skill bank." in payload["blockers"]
    gates = {gate["id"]: gate for gate in payload["gates"]}
    assert gates["book"]["status"] == "ready"
    assert gates["market"]["status"] == "locked"
    assert gates["prerequisites"]["status"] == "locked"
    assert gates["publish"]["status"] == "locked"


def test_publish_rejects_incomplete_gates(
    client,
    teacher_auth_headers,
):
    course_id = _create_course(client, teacher_auth_headers, title="Incomplete Course")

    response = client.post(
        f"/courses/{course_id}/publish",
        headers=teacher_auth_headers,
    )

    assert response.status_code == 400
    assert "Complete the book skill bank." in response.json()["detail"]["blockers"]


def test_readiness_unlocks_market_after_book_gate_passes(
    client,
    db_session,
    teacher_auth_headers,
):
    course_id = _create_course(client, teacher_auth_headers, title="Book Complete")
    _mark_book_gate_complete(db_session, course_id)

    response = client.get(
        f"/courses/{course_id}/readiness",
        headers=teacher_auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    gates = {gate["id"]: gate for gate in payload["gates"]}
    assert gates["market"]["status"] == "ready"
    assert gates["prerequisites"]["status"] == "locked"
    assert gates["publish"]["status"] == "locked"
    assert payload["next_action"]["id"] == "market"


def test_readiness_unlocks_prerequisites_after_book_and_market_gates_pass(
    client,
    db_session,
    teacher_auth_headers,
):
    course_id = _create_course(client, teacher_auth_headers, title="Market Complete")
    _mark_book_gate_complete(db_session, course_id)
    _mark_market_gate_complete(db_session, course_id)

    response = client.get(
        f"/courses/{course_id}/readiness",
        headers=teacher_auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    gates = {gate["id"]: gate for gate in payload["gates"]}
    assert gates["prerequisites"]["status"] == "ready"
    assert gates["publish"]["status"] == "locked"
    assert payload["next_action"]["id"] == "prerequisites"


def test_readiness_unlocks_publish_when_all_gates_pass_but_course_is_draft(
    client,
    db_session,
    teacher_auth_headers,
):
    course_id = _create_course(client, teacher_auth_headers, title="Ready Draft")
    _mark_book_gate_complete(db_session, course_id)
    _mark_market_gate_complete(db_session, course_id)
    _mark_prerequisites_approved(db_session, course_id)

    response = client.get(
        f"/courses/{course_id}/readiness",
        headers=teacher_auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    gates = {gate["id"]: gate for gate in payload["gates"]}
    assert gates["publish"]["status"] == "ready"
    assert payload["next_action"]["id"] == "publish"


def test_publish_succeeds_when_all_required_gates_pass(
    client,
    db_session,
    teacher_auth_headers,
):
    course_id = _create_course(client, teacher_auth_headers, title="Ready Course")
    _mark_book_gate_complete(db_session, course_id)
    _mark_market_gate_complete(db_session, course_id)
    _mark_prerequisites_approved(db_session, course_id)

    response = client.post(
        f"/courses/{course_id}/publish",
        headers=teacher_auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["publication_status"] == "published"

    readiness_response = client.get(
        f"/courses/{course_id}/readiness",
        headers=teacher_auth_headers,
    )
    assert readiness_response.status_code == 200
    readiness = readiness_response.json()
    gates = {gate["id"]: gate for gate in readiness["gates"]}
    assert readiness["next_action"]["id"] == "none"
    assert gates["publish"]["status"] == "complete"


def test_stale_prerequisites_pause_new_enrollment_without_removing_existing_student(
    client,
    db_session,
    teacher_auth_headers,
    student_auth_headers,
):
    course_id = _create_course(client, teacher_auth_headers, title="Stale Course")
    _mark_book_gate_complete(db_session, course_id)
    _mark_market_gate_complete(db_session, course_id)
    _mark_prerequisites_approved(db_session, course_id)

    publish_response = client.post(
        f"/courses/{course_id}/publish",
        headers=teacher_auth_headers,
    )
    assert publish_response.status_code == 200

    join_response = client.post(
        f"/courses/{course_id}/join",
        headers=student_auth_headers,
    )
    assert join_response.status_code == 201

    review = db_session.get(PrerequisiteReview, course_id)
    assert review is not None
    review.review_status = PrerequisiteReviewStatus.STALE
    db_session.add(review)
    db_session.commit()

    public_response = client.get("/courses")
    assert public_response.status_code == 200
    assert all(c["id"] != course_id for c in public_response.json())

    enrolled_response = client.get("/courses/enrolled", headers=student_auth_headers)
    assert enrolled_response.status_code == 200
    assert any(c["id"] == course_id for c in enrolled_response.json())
