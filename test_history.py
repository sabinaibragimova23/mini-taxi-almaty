
import sqlite3
import pytest
import app as taxi_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(taxi_app, "DB_PATH", str(tmp_path / "test_taxi.db"))
    taxi_app.app.config["TESTING"] = True
    taxi_app.init_db(force=True)

    with taxi_app.app.test_client() as c:
        yield c


def login(client, role, phone):
    response = client.post(
        "/api/login",
        json={
            "role": role,
            "phone": phone,
            "password": "demo123"
        }
    )
    assert response.status_code == 200, response.get_json()
    return {"Authorization": "Bearer " + response.get_json()["token"]}


def passenger(client):
    return login(client, "passenger", "+7 701 214 55 10")


def driver(client):
    return login(client, "driver", "+7 701 555 20 11")


def create_ride(passenger_id, driver_id, status="completed"):
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
        (
            passenger_id,
            driver_id,
            driver_id,
            "KBTU",
            "Dostyk Plaza",
            "2026-11-16 12:00",
            status,
            1000
        )
    )

    ride_id = cursor.lastrowid
    connection.commit()
    connection.close()

    return ride_id


# TEST 1: Passenger can access their ride history
def test_passenger_can_view_ride_history(client):
    token = passenger(client)
    create_ride(1, 1)

    response = client.get("/api/my/rides", headers=token)

    assert response.status_code == 200
    assert len(response.get_json()) >= 1


# TEST 2: Passenger sees only their own rides
def test_passenger_sees_only_own_rides(client):
    token = passenger(client)

    own_ride = create_ride(1, 1)
    other_ride = create_ride(2, 1)

    response = client.get("/api/my/rides", headers=token)
    ride_ids = [ride["ride_id"] for ride in response.get_json()]

    assert response.status_code == 200
    assert own_ride in ride_ids
    assert other_ride not in ride_ids


# TEST 3: Passenger history requires authentication
def test_passenger_history_without_auth(client):
    response = client.get("/api/my/rides")

    assert response.status_code == 401


# TEST 4: Driver cannot access passenger history
def test_driver_cannot_access_passenger_history(client):
    token = driver(client)

    response = client.get("/api/my/rides", headers=token)

    assert response.status_code == 403


# TEST 5: Driver can access their ride history
def test_driver_can_view_ride_history(client):
    token = driver(client)
    create_ride(1, 1)

    response = client.get("/api/driver/rides", headers=token)

    assert response.status_code == 200
    assert len(response.get_json()) >= 1


# TEST 6: Driver sees only rides assigned to them
def test_driver_sees_only_assigned_rides(client):
    token = driver(client)

    own_ride = create_ride(1, 1)
    other_ride = create_ride(1, 2)

    response = client.get("/api/driver/rides", headers=token)
    ride_ids = [ride["ride_id"] for ride in response.get_json()]

    assert response.status_code == 200
    assert own_ride in ride_ids
    assert other_ride not in ride_ids


# TEST 7: Driver history requires authentication
def test_driver_history_without_auth(client):
    response = client.get("/api/driver/rides")

    assert response.status_code == 401


# TEST 8: Passenger cannot access driver history
def test_passenger_cannot_access_driver_history(client):
    token = passenger(client)

    response = client.get("/api/driver/rides", headers=token)

    assert response.status_code == 403


# TEST 9: Driver phone is not exposed in driver history
def test_driver_phone_is_hidden(client):
    token = driver(client)
    create_ride(1, 1)

    response = client.get("/api/driver/rides", headers=token)
    ride = response.get_json()[0]

    assert response.status_code == 200
    assert "driver_phone" not in ride


# TEST 10: Passenger phone is hidden for completed rides
def test_passenger_phone_hidden_for_completed_ride(client):
    token = driver(client)
    create_ride(1, 1, status="completed")

    response = client.get("/api/driver/rides", headers=token)
    ride = response.get_json()[0]

    assert response.status_code == 200
    assert ride["passenger_phone"] is None


# TEST 11: Passenger phone is available for an active ride
def test_passenger_phone_visible_for_requested_ride(client):
    token = driver(client)
    create_ride(1, 1, status="requested")

    response = client.get("/api/driver/rides", headers=token)
    ride = response.get_json()[0]

    assert response.status_code == 200
    assert ride["passenger_phone"] is not None
