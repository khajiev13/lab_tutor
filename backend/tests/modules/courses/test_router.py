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


def _publish_course_directly(db_session, course_id: int) -> None:
    course = db_session.get(Course, course_id)
    assert course is not None
    course.publication_status = CoursePublicationStatus.PUBLISHED
    db_session.add(course)
    db_session.commit()


def _mark_readiness_gates_complete(db_session, course_id: int) -> None:
    db_session.add(
        BookSelectionSession(
            course_id=course_id,
            thread_id=f"router-book-session-{course_id}",
            status=SessionStatus.COMPLETED,
        )
    )
    course = db_session.get(Course, course_id)
    assert course is not None
    course.market_gate_status = CourseMarketGateStatus.COMPLETED
    db_session.add(
        PrerequisiteReview(
            course_id=course_id,
            review_status=PrerequisiteReviewStatus.APPROVED,
            draft_edges=[],
            isolated_skills_viewed=True,
        )
    )
    db_session.add(course)
    db_session.commit()


def test_create_course(client, teacher_auth_headers):
    response = client.post(
        "/courses",
        json={"title": "Test Course", "description": "A test course"},
        headers=teacher_auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Course"
    assert data["extraction_status"] == "not_started"


def test_upload_presentation(client, teacher_auth_headers, mock_blob_service):
    # First create a course
    create_res = client.post(
        "/courses",
        json={"title": "Test Course", "description": "A test course"},
        headers=teacher_auth_headers,
    )
    course_id = create_res.json()["id"]

    # Upload file
    files = {"files": ("test.pdf", b"file content", "application/pdf")}
    response = client.post(
        f"/courses/{course_id}/presentations",
        files=files,
        headers=teacher_auth_headers,
    )
    assert response.status_code == 201
    assert "uploaded_files" in response.json()
    mock_blob_service.upload_bytes.assert_called()


def test_presentation_statuses_endpoint(
    client, teacher_auth_headers, mock_blob_service
):
    create_res = client.post(
        "/courses",
        json={"title": "Test Course", "description": "A test course"},
        headers=teacher_auth_headers,
    )
    course_id = create_res.json()["id"]

    files = {"files": ("test.pdf", b"file content", "application/pdf")}
    client.post(
        f"/courses/{course_id}/presentations",
        files=files,
        headers=teacher_auth_headers,
    )

    res = client.get(
        f"/courses/{course_id}/presentations/status",
        headers=teacher_auth_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["filename"] == "test.pdf"
    assert data[0]["status"] == "pending"


def test_start_extraction(client, teacher_auth_headers):
    # Create course
    create_res = client.post(
        "/courses",
        json={"title": "Test Course", "description": "A test course"},
        headers=teacher_auth_headers,
    )
    course_id = create_res.json()["id"]

    # Start extraction
    response = client.post(
        f"/courses/{course_id}/extract",
        headers=teacher_auth_headers,
    )
    assert response.status_code == 202
    # In tests, BackgroundTasks may run to completion before we fetch the course.
    assert response.json()["status"] in ("in_progress", "finished", "failed")

    # Verify DB state
    # We can check via API or DB session. Let's check via API.
    get_res = client.get(f"/courses/{course_id}", headers=teacher_auth_headers)
    assert get_res.json()["extraction_status"] in ("in_progress", "finished", "failed")


def test_upload_presentation_locked(
    client, teacher_auth_headers, mock_blob_service, monkeypatch
):
    # Create course
    create_res = client.post(
        "/courses",
        json={"title": "Test Course", "description": "A test course"},
        headers=teacher_auth_headers,
    )
    course_id = create_res.json()["id"]

    # Upload at least one pending file so extraction transitions to IN_PROGRESS.
    client.post(
        f"/courses/{course_id}/presentations",
        files={"files": ("seed.txt", b"seed content", "text/plain")},
        headers=teacher_auth_headers,
    )

    # Make the background task a no-op so the course stays IN_PROGRESS deterministically.
    monkeypatch.setattr(
        "app.modules.courses.service.run_course_extraction_background",
        lambda *args, **kwargs: None,
    )

    # Start extraction
    client.post(f"/courses/{course_id}/extract", headers=teacher_auth_headers)

    # Try to upload file
    files = {"files": ("test.pdf", b"file content", "application/pdf")}
    response = client.post(
        f"/courses/{course_id}/presentations",
        files=files,
        headers=teacher_auth_headers,
    )
    assert response.status_code == 400
    assert "extraction is in progress" in response.json()["detail"]


def test_delete_presentation_locked(
    client, teacher_auth_headers, mock_blob_service, monkeypatch
):
    # Create course
    create_res = client.post(
        "/courses",
        json={"title": "Test Course", "description": "A test course"},
        headers=teacher_auth_headers,
    )
    course_id = create_res.json()["id"]

    client.post(
        f"/courses/{course_id}/presentations",
        files={"files": ("seed.txt", b"seed content", "text/plain")},
        headers=teacher_auth_headers,
    )
    monkeypatch.setattr(
        "app.modules.courses.service.run_course_extraction_background",
        lambda *args, **kwargs: None,
    )

    # Start extraction
    client.post(f"/courses/{course_id}/extract", headers=teacher_auth_headers)

    # Try to delete file
    response = client.delete(
        f"/courses/{course_id}/presentations/test.pdf",
        headers=teacher_auth_headers,
    )
    assert response.status_code == 400
    assert "extraction is in progress" in response.json()["detail"]


def test_list_courses(client, teacher_auth_headers):
    # Create a course
    course_1 = client.post(
        "/courses",
        json={"title": "Course 1", "description": "Desc 1"},
        headers=teacher_auth_headers,
    )
    course_2 = client.post(
        "/courses",
        json={"title": "Course 2", "description": "Desc 2"},
        headers=teacher_auth_headers,
    )
    assert course_1.status_code == 201
    assert course_2.status_code == 201

    response = client.get("/courses")
    assert response.status_code == 200
    data = response.json()
    created_ids = {course_1.json()["id"], course_2.json()["id"]}
    assert all(c["id"] not in created_ids for c in data)


def test_update_course(client, teacher_auth_headers):
    # Create course
    create_res = client.post(
        "/courses",
        json={"title": "Old Title", "description": "Old Desc"},
        headers=teacher_auth_headers,
    )
    course_id = create_res.json()["id"]

    # Update course
    response = client.put(
        f"/courses/{course_id}",
        json={"title": "New Title", "description": "New Desc"},
        headers=teacher_auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "New Title"
    assert data["description"] == "New Desc"


def test_delete_course(client, teacher_auth_headers):
    # Create course
    create_res = client.post(
        "/courses",
        json={"title": "To Delete", "description": "Desc"},
        headers=teacher_auth_headers,
    )
    course_id = create_res.json()["id"]

    # Delete course
    response = client.delete(f"/courses/{course_id}", headers=teacher_auth_headers)
    assert response.status_code == 204

    # Verify deleted
    get_res = client.get(f"/courses/{course_id}", headers=teacher_auth_headers)
    assert get_res.status_code == 404


def test_join_course(client, db_session, teacher_auth_headers, student_auth_headers):
    # Create course (as teacher)
    create_res = client.post(
        "/courses",
        json={"title": "Course to Join", "description": "Desc"},
        headers=teacher_auth_headers,
    )
    course_id = create_res.json()["id"]
    _mark_readiness_gates_complete(db_session, course_id)
    _publish_course_directly(db_session, course_id)

    # Join course (as student)
    response = client.post(
        f"/courses/{course_id}/join",
        headers=student_auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["course_id"] == course_id

    # Try to join again (should fail)
    response = client.post(
        f"/courses/{course_id}/join",
        headers=student_auth_headers,
    )
    assert response.status_code == 400


def test_delete_all_presentations_locked(
    client, teacher_auth_headers, mock_blob_service, monkeypatch
):
    # Create course
    create_res = client.post(
        "/courses",
        json={"title": "Test Course", "description": "A test course"},
        headers=teacher_auth_headers,
    )
    course_id = create_res.json()["id"]

    client.post(
        f"/courses/{course_id}/presentations",
        files={"files": ("seed.txt", b"seed content", "text/plain")},
        headers=teacher_auth_headers,
    )
    monkeypatch.setattr(
        "app.modules.courses.service.run_course_extraction_background",
        lambda *args, **kwargs: None,
    )

    # Start extraction
    client.post(f"/courses/{course_id}/extract", headers=teacher_auth_headers)

    # Try to delete all files
    response = client.delete(
        f"/courses/{course_id}/presentations",
        headers=teacher_auth_headers,
    )
    assert response.status_code == 400
    assert "extraction is in progress" in response.json()["detail"]
