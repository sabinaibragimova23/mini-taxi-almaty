
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


# Passenger login
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


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


# Create a completed ride for testing
def create_completed_ride(client):
    connection = sqlite3.connect(taxi_app.DB_PATH)

    cursor = connection.execute(
        """
        INSERT INTO rides (
            passenger_id, driver_id, car_id,
            pickup_address, dropoff_address,
            start_time, status, price
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (1, 1, 1, "KBTU", "Dostyk Plaza",
         "2026-11-16 12:00", "completed", 1000)
    )

    ride_id = cursor.lastrowid
    connection.commit()
    connection.close()

    return ride_id


# TEST 1: Successful rating
def test_successful_rating(client):
    token = login_passenger(client)
    ride_id = create_completed_ride(client)

    response = client.post(
        f"/api/rides/{ride_id}/rate",
        json={"rating": 5},
        headers=auth_headers(token)
    )

    data = response.get_json()

    assert response.status_code == 200
    assert data["ride_rating"] == 5
    assert data["driver_rating"] == 5.0


# TEST 2: Rating without authentication
def test_rating_without_authentication(client):
    ride_id = create_completed_ride(client)

    response = client.post(
        f"/api/rides/{ride_id}/rate",
        json={"rating": 5}
    )

    assert response.status_code == 401


# TEST 3: Rating below 1
def test_rating_below_minimum(client):
    token = login_passenger(client)
    ride_id = create_completed_ride(client)

    response = client.post(
        f"/api/rides/{ride_id}/rate",
        json={"rating": 0},
        headers=auth_headers(token)
    )

    assert response.status_code == 400


# TEST 4: Rating above 5
def test_rating_above_maximum(client):
    token = login_passenger(client)
    ride_id = create_completed_ride(client)

    response = client.post(
        f"/api/rides/{ride_id}/rate",
        json={"rating": 6},
        headers=auth_headers(token)
    )

    assert response.status_code == 400


# TEST 5: Low rating requires a comment
def test_low_rating_without_comment(client):
    token = login_passenger(client)
    ride_id = create_completed_ride(client)

    response = client.post(
        f"/api/rides/{ride_id}/rate",
        json={"rating": 2},
        headers=auth_headers(token)
    )

    assert response.status_code == 400


# TEST 6: Comment longer than 1000 characters
def test_rating_comment_too_long(client):
    token = login_passenger(client)
    ride_id = create_completed_ride(client)

    response = client.post(
        f"/api/rides/{ride_id}/rate",
        json={
            "rating": 5,
            "comment": "A" * 1001
        },
        headers=auth_headers(token)
    )

    assert response.status_code == 400


# TEST 7: Cannot rate an active ride
def test_rating_active_ride(client):
    token = login_passenger(client)

    response = client.post(
        "/api/rides",
        json={
            "pickup": "KBTU (59 Tole Bi St)",
            "dropoff": "Dostyk Plaza"
        },
        headers=auth_headers(token)
    )

    assert response.status_code == 201
    ride_id = response.get_json()["ride_id"]

    rating_response = client.post(
        f"/api/rides/{ride_id}/rate",
        json={"rating": 5},
        headers=auth_headers(token)
    )

    assert rating_response.status_code == 409


# TEST 8: Cannot rate the same ride twice
def test_duplicate_rating(client):
    token = login_passenger(client)
    ride_id = create_completed_ride(client)
    headers = auth_headers(token)

    first = client.post(
        f"/api/rides/{ride_id}/rate",
        json={"rating": 5},
        headers=headers
    )

    second = client.post(
        f"/api/rides/{ride_id}/rate",
        json={"rating": 4},
        headers=headers
    )

    assert first.status_code == 200
    assert second.status_code == 409


# TEST 9: Passenger cannot rate another passenger's ride
def test_rating_other_passengers_ride(client):
    token = login_passenger(client)

    connection = sqlite3.connect(taxi_app.DB_PATH)
    cursor = connection.execute(
        """
        INSERT INTO rides (
            passenger_id, driver_id, car_id,
            pickup_address, dropoff_address,
            start_time, status, price
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (2, 1, 1, "KBTU", "Dostyk Plaza",
         "2026-11-16 12:00", "completed", 1000)
    )

    ride_id = cursor.lastrowid
    connection.commit()
    connection.close()

    response = client.post(
        f"/api/rides/{ride_id}/rate",
        json={"rating": 5},
        headers=auth_headers(token)
    )

    assert response.status_code == 403


# TEST 10: Rating is saved in database
def test_rating_saved_in_database(client):
    token = login_passenger(client)
    ride_id = create_completed_ride(client)

    response = client.post(
        f"/api/rides/{ride_id}/rate",
        json={
            "rating": 4,
            "comment": "Good ride"
        },
        headers=auth_headers(token)
    )

    assert response.status_code == 200

    connection = sqlite3.connect(taxi_app.DB_PATH)

    ride = connection.execute(
        "SELECT ride_rating, ride_comment FROM rides WHERE ride_id = ?",
        (ride_id,)
    ).fetchone()

    driver_rating = connection.execute(
        "SELECT rating FROM drivers WHERE driver_id = 1"
    ).fetchone()[0]

    connection.close()

    assert ride == (4, "Good ride")
    assert driver_rating == 4.0
