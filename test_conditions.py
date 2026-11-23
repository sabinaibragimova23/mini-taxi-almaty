"""Tests for live conditions: traffic, accident, weather change the price. Run: python -m pytest"""
import pytest
import app as taxi_app

ROUTE = {"pickup": "Esentai Mall", "dropoff": "Mega Alma-Ata Mall"}          # both in Bostandyk
MEDEU_ROUTE = {"pickup": "Green Bazaar", "dropoff": "Panfilov Park"}        # both in Medeu


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(taxi_app, "DB_PATH", str(tmp_path / "test_taxi.db"))
    taxi_app.app.config["TESTING"] = True
    taxi_app.init_db(force=True)
    with taxi_app.app.test_client() as c:
        yield c


def login(client, **creds):
    r = client.post("/api/login", json=creds)
    return {"Authorization": "Bearer " + r.get_json()["token"]}


def admin(client):
    return login(client, role="admin", password="admin123")


def passenger(client):
    return login(client, role="passenger", login="aigerim.s@mail.kz", password="demo123")


def set_cond(client, **values):
    return client.post("/api/conditions", json=values, headers=admin(client))


def quote(client, route=ROUTE):
    return client.post("/api/quote", json=route).get_json()


def keys(q):
    return {l["rule"] for l in q["lines"]}


# TEST 1: with default conditions nothing extra is added and the public endpoint works
def test_default_conditions(client):
    c = client.get("/api/conditions").get_json()
    assert (c["traffic"], c["accident_district"], c["weather"]) == ("free", "", "clear")
    assert "Medeu" in c["districts"]
    q = quote(client)
    assert not keys(q) & {"traffic_moderate", "traffic_heavy", "accident", "rain", "snow"}


# TEST 2: heavy traffic raises the price and shows its own line; lines still add up to the total
def test_heavy_traffic_raises_price(client):
    before = quote(client)
    assert set_cond(client, traffic="heavy").status_code == 200
    after = quote(client)
    assert "traffic_heavy" in keys(after) and after["price"] > before["price"]
    assert sum(l["kzt"] for l in after["lines"]) == after["price"]
    assert "traffic_heavy" in after["extras"]


# TEST 3: moderate traffic is smaller than heavy traffic
def test_moderate_is_cheaper_than_heavy(client):
    set_cond(client, traffic="moderate")
    moderate = quote(client)["price"]
    set_cond(client, traffic="heavy")
    assert moderate < quote(client)["price"]


# TEST 4: an accident only costs extra on routes that touch that district
def test_accident_only_in_its_district(client):
    set_cond(client, accident_district="Medeu")
    assert "accident" not in keys(quote(client, ROUTE))
    assert "accident" in keys(quote(client, MEDEU_ROUTE))
    # one end in the district is enough
    assert "accident" in keys(quote(client, {"pickup": "Esentai Mall", "dropoff": "Green Bazaar"}))


# TEST 5: rain and snow are separate charges, and clear weather has none
def test_rain_and_snow(client):
    set_cond(client, weather_mode="rain")
    rain = quote(client)
    assert "rain" in keys(rain) and "snow" not in keys(rain)
    set_cond(client, weather_mode="snow")
    snow = quote(client)
    assert "snow" in keys(snow) and "rain" not in keys(snow)
    assert snow["price"] > rain["price"]
    set_cond(client, weather_mode="clear")
    assert not keys(quote(client)) & {"rain", "snow"}


# TEST 6: the admin can switch a condition price off in the Prices tab
def test_switching_a_rule_off_removes_the_charge(client):
    set_cond(client, weather_mode="rain")
    assert "rain" in keys(quote(client))
    r = client.post("/api/fare_rules/rain", json={"amount": 1.1, "active": False}, headers=admin(client))
    assert r.status_code == 200
    assert "rain" not in keys(quote(client))


# TEST 7: all multipliers together never raise a price more than x2
def test_total_extra_is_capped(client):
    base = quote(client)["price"]
    for rule in ("traffic_heavy", "accident", "snow"):
        client.post(f"/api/fare_rules/{rule}", json={"amount": 2.0, "active": True}, headers=admin(client))
    set_cond(client, traffic="heavy", accident_district="Bostandyk", weather_mode="snow")
    assert quote(client)["price"] <= 2 * base + 10        # +10 because of rounding to 10 tenge


# TEST 8: only the admin can change conditions; bad values are rejected
def test_only_admin_changes_conditions(client):
    assert client.post("/api/conditions", json={"traffic": "heavy"}).status_code == 401
    assert client.post("/api/conditions", json={"traffic": "heavy"}, headers=passenger(client)).status_code == 403
    assert set_cond(client, traffic="gridlock").status_code == 400
    assert set_cond(client, accident_district="Mars").status_code == 400
    assert set_cond(client, weather_mode="hail").status_code == 400
    assert client.get("/api/conditions").get_json()["traffic"] == "free"      # nothing changed


# TEST 9: the price saved at booking includes the conditions of that moment
def test_booking_uses_current_conditions(client):
    set_cond(client, traffic="heavy", weather_mode="snow")
    expected = quote(client)["price"]
    r = client.post("/api/rides", json=ROUTE, headers=passenger(client))
    assert r.status_code in (200, 201)
    assert r.get_json()["price"] == expected


# TEST 10: old rides and time-only quotes ignore live conditions
def test_quote_without_conditions_ignores_them(client):
    set_cond(client, traffic="heavy", weather_mode="snow")
    with taxi_app.app.app_context():
        q = taxi_app.quote(ROUTE["pickup"], ROUTE["dropoff"])
    assert not set(q["extras"]) & {"traffic_heavy", "snow"}


# TEST 11: weather codes from the weather service are read correctly
@pytest.mark.parametrize("code, rain, snow, expected", [
    (0, 0, 0, "clear"), (3, 0, 0, "clear"),
    (61, 1.2, 0, "rain"), (80, 0, 0, "rain"), (95, 0, 0, "rain"),
    (73, 0, 0, "snow"), (0, 0, 0.4, "snow"), (71, 0, 0, "snow"),
])
def test_weather_kind(code, rain, snow, expected):
    assert taxi_app.weather_kind(code, rain, snow) == expected


# TEST 12: if the weather service is down the price still works (weather = clear)
def test_weather_service_down_does_not_break_prices(client, monkeypatch):
    monkeypatch.setenv("WEATHER_AUTO", "1")
    monkeypatch.setattr(taxi_app, "_weather_cache", {"at": 0.0, "data": None})

    def boom(*a, **k):
        raise OSError("no internet")
    monkeypatch.setattr(taxi_app.urllib.request, "urlopen", boom)
    c = client.get("/api/conditions").get_json()
    assert c["weather"] == "clear" and c["weather_source"] == "unavailable"
    assert quote(client)["price"] > 0
