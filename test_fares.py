"""Tests for fare rules and the price panel. Run: python -m pytest"""
from datetime import datetime

import pytest
import app as taxi_app

ROUTE = {"pickup": "Almaty Airport", "dropoff": "Esentai Mall"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(taxi_app, "DB_PATH", str(tmp_path / "test_taxi.db"))
    taxi_app.app.config["TESTING"] = True
    taxi_app.init_db(force=True)
    with taxi_app.app.test_client() as c:
        yield c


def admin(client):
    r = client.post("/api/login", json={"role": "admin", "password": "admin123"})
    return {"Authorization": "Bearer " + r.get_json()["token"]}


def passenger(client):
    r = client.post("/api/login", json={"role": "passenger", "phone": "+7 701 214 55 10", "password": "demo123"})
    return {"Authorization": "Bearer " + r.get_json()["token"]}


def quote_at(when, pickup, dropoff):
    with taxi_app.app.app_context():
        return taxi_app.quote(pickup, dropoff, when)


# TEST 1: the price panel lists all 12 prices (7 + 5 live conditions), no login needed
def test_price_panel_lists_all_prices(client):
    fares = client.get("/api/fares").get_json()
    assert {f["rule_key"] for f in fares} == {"base", "per_km", "minimum", "mountain", "airport", "night", "rush",
                                              "traffic_moderate", "traffic_heavy", "accident", "rain", "snow"}


# TEST 2: the lines of the price always add up to the total
def test_breakdown_adds_up(client):
    for when in (datetime(2026, 11, 18, 8, 30), datetime(2026, 11, 21, 23, 30), datetime(2026, 11, 22, 13, 0)):
        for p, d in (("Almaty Airport", "Esentai Mall"), ("Medeu", "Kok-Tobe"), ("Arbat (Zhibek Zholy St)", "Green Bazaar")):
            q = quote_at(when, p, d)
            assert sum(line["kzt"] for line in q["lines"]) == q["price"]


# TEST 3: airport, mountain, night and rush hour are applied when they should be
def test_extra_charges_applied(client):
    rush = quote_at(datetime(2026, 11, 18, 8, 30), "Almaty Airport", "Esentai Mall")   # Wednesday 08:30
    assert rush["airport"] and rush["rush"] and not rush["night"]
    night = quote_at(datetime(2026, 11, 21, 23, 30), "Medeu", "Kok-Tobe")             # Saturday 23:30
    assert night["mountain"] and night["night"] and not night["rush"]


# TEST 4: a short ride costs the minimum fare
def test_minimum_fare(client):
    q = quote_at(datetime(2026, 11, 22, 13, 0), "Arbat (Zhibek Zholy St)", "Green Bazaar")
    assert q["price"] == 800


# TEST 5: the admin changes a price and the next quote uses it
def test_admin_changes_price(client):
    when = datetime(2026, 11, 22, 13, 0)   # Sunday afternoon: no night, no rush
    before = quote_at(when, "Almaty Airport", "Esentai Mall")["price"]
    r = client.post("/api/fare_rules/airport", json={"amount": 1000}, headers=admin(client))
    assert r.status_code == 200
    assert quote_at(when, "Almaty Airport", "Esentai Mall")["price"] == before + 600


# TEST 6: switching an extra charge off removes it from the price and from the panel
def test_switch_extra_off(client):
    client.post("/api/fare_rules/airport", json={"active": False}, headers=admin(client))
    q = quote_at(datetime(2026, 11, 22, 13, 0), "Almaty Airport", "Esentai Mall")
    assert not q["airport"]
    assert "airport" not in {f["rule_key"] for f in client.get("/api/fares").get_json()}


# TEST 7: a booked ride keeps its price after the admin changes prices
def test_booked_ride_keeps_price(client):
    ride = client.post("/api/rides", json=ROUTE, headers=passenger(client)).get_json()
    client.post("/api/fare_rules/per_km", json={"amount": 300}, headers=admin(client))
    rides = client.get("/api/my/rides", headers=passenger(client)).get_json()
    assert [r["price"] for r in rides if r["ride_id"] == ride["ride_id"]] == [ride["price"]]


# TEST 8: wrong values are refused
def test_wrong_values_refused(client):
    a = admin(client)
    assert client.post("/api/fare_rules/base", json={"active": False}, headers=a).status_code == 400
    assert client.post("/api/fare_rules/night", json={"amount": 5}, headers=a).status_code == 400
    assert client.post("/api/fare_rules/airport", json={"amount": -100}, headers=a).status_code == 400
    assert client.post("/api/fare_rules/nothing", json={"amount": 100}, headers=a).status_code == 404


# TEST 9: only the admin can change prices
def test_only_admin_changes_prices(client):
    assert client.post("/api/fare_rules/airport", json={"amount": 1}, headers=passenger(client)).status_code == 403
    assert client.post("/api/fare_rules/airport", json={"amount": 1}).status_code == 401
