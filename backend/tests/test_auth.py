import uuid

from app.modules.auth.models import UserRole


def test_register_and_login(client, db_session):
    email = f"test_{uuid.uuid4()}@example.com"
    password = "testpassword"

    # Register
    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "first_name": "Test",
            "last_name": "User",
            "role": UserRole.STUDENT.value,
        },
    )
    assert response.status_code == 201

    # Login
    response = client.post(
        "/auth/jwt/login",
        data={"username": email, "password": password},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_invalid_credentials(client, db_session):
    email = "test2@example.com"
    password = "testpassword"

    # Register
    client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "first_name": "Test",
            "last_name": "User",
            "role": UserRole.STUDENT.value,
        },
    )

    # Login with wrong password
    response = client.post(
        "/auth/jwt/login",
        data={"username": email, "password": "wrongpassword"},
    )
    assert response.status_code == 400
