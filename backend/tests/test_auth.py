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
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


def test_refresh_token_success(client, db_session):
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
    login_data = response.json()
    assert "access_token" in login_data
    assert "refresh_token" in login_data

    # Refresh
    response = client.post(
        "/auth/jwt/refresh",
        json={"refresh_token": login_data["refresh_token"]},
    )
    assert response.status_code == 200
    refresh_data = response.json()
    assert "access_token" in refresh_data
    assert "refresh_token" in refresh_data
    assert refresh_data["token_type"] == "bearer"


def test_refresh_token_invalid(client, db_session):
    response = client.post("/auth/jwt/refresh", json={"refresh_token": "not-a-token"})
    assert response.status_code == 401


def test_login_invalid_credentials(client, db_session):
    email = f"test_{uuid.uuid4()}@example.com"
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
    assert response.status_code == 401
