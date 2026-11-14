"""Tests for driver shifts (online / offline). Run: python -m pytest"""
import pytest
import app as taxi_app

RIDE = {"pickup": "KBTU (59 Tole Bi St)", "dropoff": "Dostyk Plaza"}
DRIVER_PHONES = ["+7 701 555 20 11", "+7 707 412 87 30", "+7 775 300 64 92",
                 "+7 702 909 15 43", "+7 747 616 02 58", "+7 778 140 39 07"]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(taxi_app, "DB_PATH", str(tmp_path / "test_taxi.db"))
    taxi_app.app.config["TESTING"] = True
    taxi_app.init_db(force=True)
    with taxi_app.app.test_client() as c:
        yield c


def login(client, role, phone):
    r = client.post("/api/login", json={"role": role, "phone": phone, "password": "demo123"})
    assert r.status_code == 200, r.get_json()
    return {"Authorization": "Bearer " + r.get_json()["token"]}


def passenger(client):
    return login(client, "passenger", "+7 701 214 55 10")


# TEST 1: demo data has drivers 1-5 online and driver 6 offline
def test_demo_online_status(client):
    assert client.get("/api/me", headers=login(client, "driver", DRIVER_PHONES[0])).get_json()["online"] is True
    assert client.get("/api/me", headers=login(client, "driver", DRIVER_PHONES[5])).get_json()["online"] is False


# TEST 2: an offline driver gets no orders
def test_offline_driver_gets_no_order(client):
    d1 = login(client, "driver", DRIVER_PHONES[0])
    assert client.post("/api/driver/offline", headers=d1).status_code == 200
    ride = client.post("/api/rides", json=RIDE, headers=passenger(client)).get_json()
    assert ride["driver_id"] != 1


# TEST 3: when everyone is offline, booking is refused
def test_all_offline_booking_refused(client):
    for phone in DRIVER_PHONES[:5]:
        client.post("/api/driver/offline", headers=login(client, "driver", phone))
    r = client.post("/api/rides", json=RIDE, headers=passenger(client))
    assert r.status_code == 409


# TEST 4: a driver who goes online gets the order
def test_online_driver_gets_order(client):
    for phone in DRIVER_PHONES[:5]:
        client.post("/api/driver/offline", headers=login(client, "driver", phone))
    d6 = login(client, "driver", DRIVER_PHONES[5])
    assert client.post("/api/driver/online", headers=d6).status_code == 200
    ride = client.post("/api/rides", json=RIDE, headers=passenger(client)).get_json()
    assert ride["driver_id"] == 6


# TEST 5: a driver cannot go offline during a ride
def test_cannot_go_offline_during_ride(client):
    ride = client.post("/api/rides", json=RIDE, headers=passenger(client)).get_json()
    dt = login(client, "driver", ride["driver_phone"])
    assert client.post("/api/driver/offline", headers=dt).status_code == 409


# TEST 6: going online twice is refused; the database allows only one open shift
def test_only_one_open_shift(client):
    d1 = login(client, "driver", DRIVER_PHONES[0])
    assert client.post("/api/driver/online", headers=d1).status_code == 409


# TEST 7: a passenger cannot change a driver's status
def test_passenger_cannot_go_online(client):
    assert client.post("/api/driver/online", headers=passenger(client)).status_code == 403


# TEST 8: the hours report works for the admin
def test_hours_report(client):
    r = client.post("/api/login", json={"role": "admin", "password": "admin123"})
    admin = {"Authorization": "Bearer " + r.get_json()["token"]}
    data = client.get("/api/reports/driver-hours", headers=admin).get_json()
    assert len(data["rows"]) > 0 and all(row["hours"] > 0 for row in data["rows"])
