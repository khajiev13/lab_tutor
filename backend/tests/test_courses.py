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
    mock_blob_service.upload_file.assert_called()


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
    assert response.json()["status"] == "in_progress"

    # Verify DB state
    # We can check via API or DB session. Let's check via API.
    get_res = client.get(f"/courses/{course_id}", headers=teacher_auth_headers)
    assert get_res.json()["extraction_status"] == "in_progress"


def test_upload_presentation_locked(client, teacher_auth_headers, mock_blob_service):
    # Create course
    create_res = client.post(
        "/courses",
        json={"title": "Test Course", "description": "A test course"},
        headers=teacher_auth_headers,
    )
    course_id = create_res.json()["id"]

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


def test_delete_presentation_locked(client, teacher_auth_headers, mock_blob_service):
    # Create course
    create_res = client.post(
        "/courses",
        json={"title": "Test Course", "description": "A test course"},
        headers=teacher_auth_headers,
    )
    course_id = create_res.json()["id"]

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
    client.post(
        "/courses",
        json={"title": "Course 1", "description": "Desc 1"},
        headers=teacher_auth_headers,
    )
    client.post(
        "/courses",
        json={"title": "Course 2", "description": "Desc 2"},
        headers=teacher_auth_headers,
    )

    response = client.get("/courses")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2
    titles = [c["title"] for c in data]
    assert "Course 1" in titles
    assert "Course 2" in titles


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


def test_join_course(client, teacher_auth_headers, student_auth_headers):
    # Create course (as teacher)
    create_res = client.post(
        "/courses",
        json={"title": "Course to Join", "description": "Desc"},
        headers=teacher_auth_headers,
    )
    course_id = create_res.json()["id"]

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
    client, teacher_auth_headers, mock_blob_service
):
    # Create course
    create_res = client.post(
        "/courses",
        json={"title": "Test Course", "description": "A test course"},
        headers=teacher_auth_headers,
    )
    course_id = create_res.json()["id"]

    # Start extraction
    client.post(f"/courses/{course_id}/extract", headers=teacher_auth_headers)

    # Try to delete all files
    response = client.delete(
        f"/courses/{course_id}/presentations",
        headers=teacher_auth_headers,
    )
    assert response.status_code == 400
    assert "extraction is in progress" in response.json()["detail"]
