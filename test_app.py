
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

    assert response.status_code == 200, response.get_json()
    return response.get_json()["token"]


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


VALID_RIDE = {
    "pickup": "KBTU (59 Tole Bi St)",
    "dropoff": "Dostyk Plaza"
}


# TEST 1: Successful booking
def test_successful_booking(client):
    token = login_passenger(client)

    response = client.post(
        "/api/rides",
        json=VALID_RIDE,
        headers=auth_headers(token)
    )

    assert response.status_code == 201
    assert response.get_json()["status"] == "requested"


# TEST 2: Booking without authentication
def test_booking_without_authentication(client):
    response = client.post(
        "/api/rides",
        json=VALID_RIDE
    )

    assert response.status_code == 401


# TEST 3: Missing pickup address
def test_booking_without_pickup(client):
    token = login_passenger(client)

    response = client.post(
        "/api/rides",
        json={"dropoff": "Dostyk Plaza"},
        headers=auth_headers(token)
    )

    assert response.status_code == 400


# TEST 4: Missing dropoff address
def test_booking_without_dropoff(client):
    token = login_passenger(client)

    response = client.post(
        "/api/rides",
        json={"pickup": "KBTU (59 Tole Bi St)"},
        headers=auth_headers(token)
    )

    assert response.status_code == 400


# TEST 5: Invalid pickup address
def test_booking_with_invalid_pickup(client):
    token = login_passenger(client)

    response = client.post(
        "/api/rides",
        json={
            "pickup": "Unknown Place",
            "dropoff": "Dostyk Plaza"
        },
        headers=auth_headers(token)
    )

    assert response.status_code == 400


# TEST 6: Invalid dropoff address
def test_booking_with_invalid_dropoff(client):
    token = login_passenger(client)

    response = client.post(
        "/api/rides",
        json={
            "pickup": "KBTU (59 Tole Bi St)",
            "dropoff": "Unknown Place"
        },
        headers=auth_headers(token)
    )

    assert response.status_code == 400


# TEST 7: Same pickup and dropoff
def test_booking_with_same_locations(client):
    token = login_passenger(client)

    response = client.post(
        "/api/rides",
        json={
            "pickup": "KBTU (59 Tole Bi St)",
            "dropoff": "KBTU (59 Tole Bi St)"
        },
        headers=auth_headers(token)
    )

    assert response.status_code == 400


# TEST 8: Duplicate active booking
def test_duplicate_active_booking(client):
    token = login_passenger(client)
    headers = auth_headers(token)

    first = client.post(
        "/api/rides",
        json=VALID_RIDE,
        headers=headers
    )

    second = client.post(
        "/api/rides",
        json=VALID_RIDE,
        headers=headers
    )

    assert first.status_code == 201
    assert second.status_code == 409


# TEST 9: Validate booking response
def test_booking_response_data(client):
    token = login_passenger(client)

    response = client.post(
        "/api/rides",
        json=VALID_RIDE,
        headers=auth_headers(token)
    )

    data = response.get_json()

    assert response.status_code == 201
    assert data["ride_id"] is not None
    assert data["driver_id"] is not None
    assert data["car_id"] is not None
    assert data["price"] >= 800
    assert data["status"] == "requested"
    assert "quote" in data


# TEST 10: Verify booking is saved in database
def test_booking_saved_in_database(client):
    token = login_passenger(client)

    response = client.post(
        "/api/rides",
        json=VALID_RIDE,
        headers=auth_headers(token)
    )

    assert response.status_code == 201

    ride_id = response.get_json()["ride_id"]

    connection = sqlite3.connect(taxi_app.DB_PATH)

    ride = connection.execute(
        "SELECT pickup_address, dropoff_address, status "
        "FROM rides WHERE ride_id = ?",
        (ride_id,)
    ).fetchone()

    connection.close()

    assert ride is not None
    assert ride[0] == VALID_RIDE["pickup"]
    assert ride[1] == VALID_RIDE["dropoff"]
    assert ride[2] == "requested"
