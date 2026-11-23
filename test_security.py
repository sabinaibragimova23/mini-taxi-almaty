
import pytest
import app as taxi_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(
        taxi_app, "DB_PATH", str(tmp_path / "test_taxi.db")
    )
    taxi_app.app.config["TESTING"] = True
    taxi_app.init_db(force=True)

    with taxi_app.app.test_client() as c:
        yield c


def login(client, role, **credentials):
    response = client.post(
        "/api/login",
        json={"role": role, **credentials}
    )
    assert response.status_code == 200, response.get_json()
    return {
        "Authorization": "Bearer " + response.get_json()["token"]
    }


def passenger(client):
    return login(
        client,
        "passenger",
        phone="+7 701 214 55 10",
        password="demo123"
    )


def driver(client):
    return login(
        client,
        "driver",
        phone="+7 701 555 20 11",
        password="demo123"
    )


def admin(client):
    return login(
        client,
        "admin",
        password="admin123"
    )


# TEST 1: Admin can access the rides management endpoint
def test_admin_can_access_all_rides(client):
    response = client.get(
        "/api/rides",
        headers=admin(client)
    )

    assert response.status_code == 200
    assert isinstance(response.get_json(), list)


# TEST 2: Passenger cannot access admin rides
def test_passenger_cannot_access_admin_rides(client):
    response = client.get(
        "/api/rides",
        headers=passenger(client)
    )

    assert response.status_code == 403


# TEST 3: Driver cannot access admin payments
def test_driver_cannot_access_admin_payments(client):
    response = client.get(
        "/api/payments",
        headers=driver(client)
    )

    assert response.status_code == 403


# TEST 4: Admin endpoints require authentication
def test_admin_endpoint_without_token(client):
    response = client.get("/api/rides")

    assert response.status_code == 401


# TEST 5: Invalid or forged token is rejected
def test_invalid_token_is_rejected(client):
    response = client.get(
        "/api/rides",
        headers={"Authorization": "Bearer invalid.fake.token"}
    )

    assert response.status_code == 401


# TEST 6: Wrong admin password is rejected
def test_admin_login_wrong_password(client):
    response = client.post(
        "/api/login",
        json={
            "role": "admin",
            "password": "wrongpassword"
        }
    )

    assert response.status_code == 401


# TEST 7: SQL injection attempt cannot log in
def test_sql_injection_login_is_rejected(client):
    response = client.post(
        "/api/login",
        json={
            "role": "passenger",
            "login": "' OR '1'='1",
            "password": "anything"
        }
    )

    assert response.status_code == 401


# TEST 8: Passenger profile does not expose password hash
def test_passenger_password_hash_is_not_exposed(client):
    response = client.get(
        "/api/me",
        headers=passenger(client)
    )

    assert response.status_code == 200

    profile = response.get_json()["profile"]

    assert "password_hash" not in profile
    assert "password" not in profile


# TEST 9: Driver profile does not expose password hash
def test_driver_password_hash_is_not_exposed(client):
    response = client.get(
        "/api/me",
        headers=driver(client)
    )

    assert response.status_code == 200

    profile = response.get_json()["profile"]

    assert "password_hash" not in profile
    assert "password" not in profile


# TEST 10: Passenger cannot reset the database
def test_passenger_cannot_reset_database(client):
    response = client.post(
        "/api/reset",
        headers=passenger(client)
    )

    assert response.status_code == 403


# TEST 11: Driver cannot reset the database
def test_driver_cannot_reset_database(client):
    response = client.post(
        "/api/reset",
        headers=driver(client)
    )

    assert response.status_code == 403


# TEST 12: Admin can reset demo database
def test_admin_can_reset_database(client):
    response = client.post(
        "/api/reset",
        headers=admin(client)
    )

    assert response.status_code == 200
    assert response.get_json()["ok"] is True

