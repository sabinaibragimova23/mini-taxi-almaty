
import sqlite3
import pytest
import app as taxi_app


# Test database fixture
@pytest.fixture
def client(tmp_path, monkeypatch):
    test_db = tmp_path / "test_taxi.db"
    monkeypatch.setattr(taxi_app, "DB_PATH", str(test_db))

    taxi_app.app.config["TESTING"] = True
    taxi_app.init_db(force=True)

    with taxi_app.app.test_client() as test_client:
        yield test_client


# Helper: login passenger
def login_passenger(client):
    response = client.post(
        "/api/login",
        json={
            "role": "passenger",
            "phone": "+7 701 214 55 10",
            "password": "demo123"
        }
    )
    assert response.status_code == 200
    return response.get_json()["token"]


# TEST 1: Successful login with phone
def test_login_with_phone(client):
    response = client.post(
        "/api/login",
        json={
            "role": "passenger",
            "phone": "+7 701 214 55 10",
            "password": "demo123"
        }
    )

    assert response.status_code == 200
    assert "token" in response.get_json()


# TEST 2: Successful login with email
def test_login_with_email(client):
    response = client.post(
        "/api/login",
        json={
            "role": "passenger",
            "login": "aigerim.s@mail.kz",
            "password": "demo123"
        }
    )

    assert response.status_code == 200
    assert "token" in response.get_json()


# TEST 3: Login with wrong password
def test_login_wrong_password(client):
    response = client.post(
        "/api/login",
        json={
            "role": "passenger",
            "phone": "+7 701 214 55 10",
            "password": "wrong123"
        }
    )

    assert response.status_code == 401


# TEST 4: Login with unknown user
def test_login_unknown_user(client):
    response = client.post(
        "/api/login",
        json={
            "role": "passenger",
            "phone": "+7 777 000 00 00",
            "password": "demo123"
        }
    )

    assert response.status_code == 401


# TEST 5: Login without password
def test_login_without_password(client):
    response = client.post(
        "/api/login",
        json={"role": "passenger", "phone": "+7 701 214 55 10"}
    )

    assert response.status_code == 400


# TEST 6: Login without identifier
def test_login_without_identifier(client):
    response = client.post(
        "/api/login",
        json={"role": "passenger", "password": "demo123"}
    )

    assert response.status_code == 400


# TEST 7: Unknown role
def test_login_unknown_role(client):
    response = client.post(
        "/api/login",
        json={"role": "unknown", "password": "demo123"}
    )

    assert response.status_code == 400


# TEST 8: Successful passenger registration
def test_successful_signup(client):
    response = client.post(
        "/api/signup",
        json={
            "full_name": "Test Passenger",
            "phone": "+7 777 123 45 67",
            "email": "test.passenger@example.com",
            "password": "password123"
        }
    )

    data = response.get_json()

    assert response.status_code == 200
    assert "token" in data
    assert data["role"] == "passenger"


# TEST 9: Registration with short password
def test_signup_short_password(client):
    response = client.post(
        "/api/signup",
        json={
            "full_name": "Test Passenger",
            "phone": "+7 777 123 45 67",
            "email": "test.passenger@example.com",
            "password": "123"
        }
    )

    assert response.status_code == 400


# TEST 10: Duplicate registration
def test_signup_duplicate_phone(client):
    client.post(
        "/api/signup",
        json={
            "full_name": "First Passenger",
            "phone": "+7 777 123 45 67",
            "email": "first@example.com",
            "password": "password123"
        }
    )

    response = client.post(
        "/api/signup",
        json={
            "full_name": "Second Passenger",
            "phone": "+7 777 123 45 67",
            "email": "second@example.com",
            "password": "password123"
        }
    )

    assert response.status_code == 409


# TEST 11: Profile requires authentication
def test_profile_without_token(client):
    response = client.get("/api/me")

    assert response.status_code == 401


# TEST 12: Password hash is not exposed
def test_password_hash_not_returned(client):
    token = login_passenger(client)

    response = client.get(
        "/api/me",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert "password_hash" not in response.get_json()["profile"]
