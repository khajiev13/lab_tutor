from __future__ import annotations


def test_embeddings_status_endpoint_returns_course_and_file_statuses(
    client, teacher_auth_headers, mock_blob_service
):
    # Create course
    create_res = client.post(
        "/courses",
        json={"title": "Embed Status Course", "description": "desc"},
        headers=teacher_auth_headers,
    )
    assert create_res.status_code == 201
    course_id = create_res.json()["id"]

    # Upload a presentation
    up = client.post(
        f"/courses/{course_id}/presentations",
        files={"files": ("one.txt", b"a" * 10, "text/plain")},
        headers=teacher_auth_headers,
    )
    assert up.status_code == 201

    # Embedding status should be available even before extraction/embedding.
    res = client.get(
        f"/courses/{course_id}/embeddings/status",
        headers=teacher_auth_headers,
    )
    assert res.status_code == 200

    data = res.json()
    assert data["course_id"] == course_id
    assert data["embedding_status"] == "not_started"
    assert isinstance(data["files"], list)
    assert len(data["files"]) == 1
    assert data["files"][0]["filename"] == "one.txt"
    assert data["files"][0]["embedding_status"] == "not_started"
