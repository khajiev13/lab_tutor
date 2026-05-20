from app.modules.courses.models import Course, CoursePublicationStatus


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
