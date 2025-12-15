from lab_tutor_backend.auth import get_password_hash
from lab_tutor_backend.models import User, UserRole


def test_login(client, db_session):
    # Create user
    password = "testpassword"
    hashed = get_password_hash(password)
    user = User(
        first_name="Test",
        last_name="User",
        email="test@example.com",
        password_hash=hashed,
        role=UserRole.STUDENT,
    )
    db_session.add(user)
    db_session.commit()

    # Login
    response = client.post(
        "/auth/login",
        json={"email": "test@example.com", "password": password},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_invalid_credentials(client, db_session):
    # Create user
    password = "testpassword"
    hashed = get_password_hash(password)
    user = User(
        first_name="Test",
        last_name="User",
        email="test@example.com",
        password_hash=hashed,
        role=UserRole.STUDENT,
    )
    db_session.add(user)
    db_session.commit()

    # Login with wrong password
    response = client.post(
        "/auth/login",
        json={"email": "test@example.com", "password": "wrongpassword"},
    )
    assert response.status_code == 401
