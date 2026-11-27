"""Tests for saved places (a passenger's favourite addresses). Run: python -m pytest"""
import pytest
import app as taxi_app

AIGERIM = {"role": "passenger", "phone": "+7 701 214 55 10", "password": "demo123"}
DANIYAR = {"role": "passenger", "phone": "+7 705 330 12 87", "password": "demo123"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(taxi_app, "DB_PATH", str(tmp_path / "test_taxi.db"))
    taxi_app.app.config["TESTING"] = True
    taxi_app.init_db(force=True)
    with taxi_app.app.test_client() as c:
        yield c


def login(client, creds):
    r = client.post("/api/login", json=creds)
    assert r.status_code == 200, r.get_json()
    return {"Authorization": "Bearer " + r.get_json()["token"]}


def admin(client):
    return login(client, {"role": "admin", "password": "admin123"})


def set_traffic(client, traffic):
    r = client.post("/api/conditions", json={"traffic": traffic, "accident_district": "", "weather_mode": "clear"},
                    headers=admin(client))
    assert r.status_code == 200, r.get_json()


# TEST 1: the demo passenger has three saved places
def test_demo_places(client):
    places = client.get("/api/my/places", headers=login(client, AIGERIM)).get_json()["places"]
    assert [p["label"] for p in places] == ["Home", "University", "Gym"]


# TEST 2: a passenger saves a new place and sees it in the list
def test_add_place(client):
    h = login(client, DANIYAR)
    r = client.post("/api/my/places", json={"label": "Work", "address": "Esentai Mall", "icon": "work"}, headers=h)
    assert r.status_code == 201
    assert [p["label"] for p in client.get("/api/my/places", headers=h).get_json()["places"]] == ["Work"]


# TEST 3: the same name twice is refused (also "home" vs "Home")
def test_same_name_refused(client):
    h = login(client, AIGERIM)
    r = client.post("/api/my/places", json={"label": "home", "address": "Mega Alma-Ata Mall"}, headers=h)
    assert r.status_code == 409


# TEST 4: two different passengers may both have a "Home"
def test_same_name_other_passenger_ok(client):
    r = client.post("/api/my/places", json={"label": "Home", "address": "Arbat (Zhibek Zholy St)", "icon": "home"},
                    headers=login(client, DANIYAR))
    assert r.status_code == 201


# TEST 5: wrong data is refused
def test_wrong_data_refused(client):
    h = login(client, DANIYAR)
    assert client.post("/api/my/places", json={"label": "", "address": "Esentai Mall"}, headers=h).status_code == 400
    assert client.post("/api/my/places", json={"label": "X", "address": "Paris"}, headers=h).status_code == 400
    assert client.post("/api/my/places", json={"label": "X", "address": "Esentai Mall", "icon": "car"}, headers=h).status_code == 400


# TEST 6: a passenger can delete only their own place
def test_delete_only_own(client):
    aigerim_place = client.get("/api/my/places", headers=login(client, AIGERIM)).get_json()["places"][0]["place_id"]
    assert client.delete(f"/api/my/places/{aigerim_place}", headers=login(client, DANIYAR)).status_code == 404
    assert client.delete(f"/api/my/places/{aigerim_place}", headers=login(client, AIGERIM)).status_code == 200


# TEST 7: each place shows price and time from the pickup; the pickup itself shows "you are here"
def test_estimates_from_pickup(client):
    data = client.get("/api/my/places?from=Sairan Lake", headers=login(client, AIGERIM)).get_json()
    by_label = {p["label"]: p["estimate"] for p in data["places"]}
    assert by_label["Home"] is None
    assert by_label["University"]["price"] >= 800 and by_label["University"]["minutes"] >= 5


# TEST 8: heavy traffic makes the trip longer and more expensive
def test_heavy_traffic_slower_and_dearer(client):
    h = login(client, AIGERIM)
    set_traffic(client, "free")
    free = client.get("/api/my/places?from=Almaty Airport", headers=h).get_json()["places"][0]["estimate"]
    set_traffic(client, "heavy")
    heavy = client.get("/api/my/places?from=Almaty Airport", headers=h).get_json()["places"][0]["estimate"]
    assert free["traffic_delay_min"] == 0
    assert heavy["minutes"] > free["minutes"] and heavy["traffic_delay_min"] > 0
    assert heavy["price"] > free["price"]


# TEST 9: only passengers use saved places; the admin sees the table
def test_access(client):
    assert client.get("/api/my/places").status_code == 401
    assert client.get("/api/my/places", headers=admin(client)).status_code == 403
    assert len(client.get("/api/saved_places", headers=admin(client)).get_json()) == 3
