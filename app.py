"""
Mini Taxi Service, Almaty: backend (Flask + SQLite)

Run:
    pip install flask
    python app.py
Open: http://127.0.0.1:5000

Database: taxi.db (created automatically from schema.sql + demo data).
Reset: delete taxi.db and run again (or the admin "Reset demo data" button).

Roles: passenger and driver log in by email (or phone) + password, admin by password
(ADMIN_PASSWORD env variable, default: admin123).
"""
import json
import math
import json
import os
import random
import re
import sqlite3
import time
import urllib.request
from datetime import datetime, timedelta, timezone

from flask import Flask, g, jsonify, request, send_from_directory
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "taxi.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")

DEMO_PASSWORD = "demo123"  # password of all demo passengers and drivers


POSITIVE_FEEDBACK_OPTIONS = {
    "Polite driver", "Clean car", "Safe driving",
    "Arrived on time", "Comfortable ride", "Friendly communication",
}
IMPROVEMENT_FEEDBACK_OPTIONS = {
    "Rude driver", "Dirty car", "Unsafe driving",
    "Driver was late", "Uncomfortable ride",
}
ALL_FEEDBACK_OPTIONS = POSITIVE_FEEDBACK_OPTIONS | IMPROVEMENT_FEEDBACK_OPTIONS
MIN_PASSWORD_LEN = 6
DEMO_DRIVER_EMAILS = {  # used only to upgrade an old taxi.db
    "+7 701 555 20 11": "bauyrzhan.t@taxi.kz", "+7 707 412 87 30": "nursultan.i@taxi.kz",
    "+7 775 300 64 92": "yerzhan.m@taxi.kz", "+7 702 909 15 43": "gulnara.a@taxi.kz",
    "+7 747 616 02 58": "ruslan.p@taxi.kz", "+7 778 140 39 07": "askhat.b@taxi.kz",
}

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.json.ensure_ascii = False


PLACES = [
    {"id": "airport",   "name": "Almaty Airport",            "district": "Turksib",   "lat": 43.3521, "lng": 77.0405},
    {"id": "almaty1",   "name": "Almaty-1 Station",            "district": "Turksib",   "lat": 43.3405, "lng": 76.9495},
    {"id": "almaty2",   "name": "Almaty-2 Station",            "district": "Almaly",   "lat": 43.2711, "lng": 76.9407},
    {"id": "bazaar",    "name": "Green Bazaar",              "district": "Medeu",     "lat": 43.2627, "lng": 76.9537},
    {"id": "panfilov",  "name": "Panfilov Park",        "district": "Medeu",     "lat": 43.2587, "lng": 76.9549},
    {"id": "arbat",     "name": "Arbat (Zhibek Zholy St)",     "district": "Almaly",   "lat": 43.2614, "lng": 76.9449},
    {"id": "kbtu",      "name": "KBTU (59 Tole Bi St)",          "district": "Almaly",   "lat": 43.2552, "lng": 76.9440},
    {"id": "republic",  "name": "Republic Square",             "district": "Medeu",     "lat": 43.2382, "lng": 76.9456},
    {"id": "dostyk",    "name": "Dostyk Plaza",               "district": "Medeu",     "lat": 43.2330, "lng": 76.9568},
    {"id": "koktobe",   "name": "Kok-Tobe",                   "district": "Medeu",     "lat": 43.2337, "lng": 76.9762},
    {"id": "satbayev",  "name": "Satbayev University",        "district": "Bostandyk", "lat": 43.2366, "lng": 76.9300},
    {"id": "stadium",   "name": "Central Stadium",        "district": "Bostandyk", "lat": 43.2370, "lng": 76.9188},
    {"id": "kaznu",     "name": "Al-Farabi KazNU",       "district": "Bostandyk", "lat": 43.2243, "lng": 76.9229},
    {"id": "esentai",   "name": "Esentai Mall",               "district": "Bostandyk", "lat": 43.2185, "lng": 76.9279},
    {"id": "botanic",   "name": "Botanical Garden",           "district": "Bostandyk", "lat": 43.2207, "lng": 76.9122},
    {"id": "mega",      "name": "Mega Alma-Ata Mall",          "district": "Bostandyk", "lat": 43.2023, "lng": 76.8924},
    {"id": "sairan",    "name": "Sairan Lake",               "district": "Auezov",    "lat": 43.2392, "lng": 76.8690},
    {"id": "arena",     "name": "Almaty Arena",               "district": "Alatau",    "lat": 43.2646, "lng": 76.8292},
    {"id": "medeu",     "name": "Medeu",                      "district": "Medeu",     "lat": 43.1575, "lng": 77.0587},
    {"id": "shymbulak", "name": "Shymbulak",                   "district": "Medeu",     "lat": 43.1281, "lng": 77.0807},
]
PLACE_BY_NAME = {p["name"]: p for p in PLACES}

# Fare (KZT)
ROAD_FACTOR = 1.35          # roads are longer than a straight line

# Prices live in the FARE_RULES table, so the admin can change them.
# These are the starting values for a new database (migration 005).
DEFAULT_FARE_RULES = [
    # rule_key, name, kind, amount, applies_to
    ("base", "Base fare", "fixed", 500, "Every ride"),
    ("per_km", "Price per km", "per_km", 140, "Every km of the route (straight line x 1.35)"),
    ("minimum", "Minimum fare", "minimum", 800, "If the ride costs less, the passenger pays this"),
    ("mountain", "Mountain surcharge", "surcharge", 600, "Pickup or drop-off at Medeu or Shymbulak"),
    ("airport", "Airport surcharge", "surcharge", 400, "Pickup or drop-off at Almaty Airport"),
    ("night", "Night fare", "multiplier", 1.2, "23:00 - 06:00"),
    ("rush", "Rush hour", "multiplier", 1.1, "07:00 - 10:00 and 17:00 - 20:00 on weekdays"),
    # live conditions (migration 007): see the CONDITIONS table below
    ("traffic_moderate", "Moderate traffic", "multiplier", 1.15, "Admin sets city traffic to Moderate"),
    ("traffic_heavy", "Heavy traffic", "multiplier", 1.3, "Admin sets city traffic to Heavy"),
    ("accident", "Accident in the area", "multiplier", 1.2, "Accident in the district of the pickup or drop-off"),
    ("rain", "Rain", "multiplier", 1.1, "It is raining in Almaty (live weather)"),
    ("snow", "Snow", "multiplier", 1.25, "It is snowing in Almaty (live weather)"),
]
CORE_RULES = ("base", "per_km", "minimum")   # always on: cannot be switched off


def load_fare_rules(con):
    """All fare rules from the database as {rule_key: row}."""
    return {r["rule_key"]: dict(r) for r in con.execute("SELECT * FROM fare_rules")}


def insert_default_fares(con):
    con.executemany("""INSERT OR IGNORE INTO fare_rules(rule_key, name, kind, amount, applies_to)
                       VALUES (?,?,?,?,?)""", DEFAULT_FARE_RULES)


# ---------------------------------------------------------------------------
# Live conditions: traffic and accidents are set by the admin, the weather comes
# from the internet (Open-Meteo, free, no key) or is set by the admin. They are
# stored in the CONDITIONS table (migration 007). Each one has a multiplier in FARE_RULES.
# ---------------------------------------------------------------------------
TRAFFIC_LEVELS = ("free", "moderate", "heavy")
WEATHER_MODES = ("auto", "clear", "rain", "snow")
DISTRICTS = sorted({p["district"] for p in PLACES})
MAX_SURGE = 2.0                 # all multipliers together never raise a price more than x2
ALMATY_LAT, ALMATY_LNG = 43.2389, 76.8897
WEATHER_TTL = 600               # ask the weather service at most once per 10 minutes
_weather_cache = {"at": 0.0, "data": None}
DEFAULT_CONDITIONS = {"traffic": "free", "accident_district": "", "weather_mode": "auto"}


def insert_default_conditions(con):
    con.executemany("INSERT OR IGNORE INTO conditions(key, value) VALUES (?,?)", list(DEFAULT_CONDITIONS.items()))


def weather_kind(code, rain_mm, snow_cm):
    """WMO weather code from Open-Meteo -> 'snow', 'rain' or 'clear'."""
    if snow_cm > 0 or code in (71, 73, 75, 77, 85, 86):
        return "snow"
    if rain_mm > 0 or code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99):
        return "rain"
    return "clear"


def fetch_weather():
    """Real weather in Almaty. Never raises: if the service is not available the weather is 'clear'.
    Set WEATHER_AUTO=0 to switch this off (the tests do)."""
    if os.environ.get("WEATHER_AUTO", "1") != "1":
        return {"kind": "clear", "temp": None, "ok": False}
    now = time.time()
    if _weather_cache["data"] is not None and now - _weather_cache["at"] < WEATHER_TTL:
        return _weather_cache["data"]
    url = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
           "&current=temperature_2m,rain,snowfall,weather_code" % (ALMATY_LAT, ALMATY_LNG))
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            cur = json.load(r)["current"]
        data = {"kind": weather_kind(cur.get("weather_code") or 0, cur.get("rain") or 0, cur.get("snowfall") or 0),
                "temp": cur.get("temperature_2m"), "ok": True}
        _weather_cache.update(at=now, data=data)
    except Exception:
        data = {"kind": "clear", "temp": None, "ok": False}
        _weather_cache.update(at=now - WEATHER_TTL + 60, data=data)   # try again in a minute
    return data


def current_conditions(con):
    """What prices are based on right now."""
    stored = dict(DEFAULT_CONDITIONS)
    stored.update({r[0]: r[1] for r in con.execute("SELECT key, value FROM conditions")})
    mode = stored["weather_mode"]
    if mode == "auto":
        w = fetch_weather()
        weather, source, temp = w["kind"], ("internet" if w["ok"] else "unavailable"), w["temp"]
    else:
        weather, source, temp = mode, "admin", None
    return {"traffic": stored["traffic"], "accident_district": stored["accident_district"],
            "weather": weather, "weather_mode": mode, "weather_source": source, "temp": temp}


def haversine_km(a, b):
    r = 6371.0
    dlat = math.radians(b["lat"] - a["lat"])
    dlng = math.radians(b["lng"] - a["lng"])
    h = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(a["lat"])) * math.cos(math.radians(b["lat"])) * math.sin(dlng / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(h))


def quote(pickup_name, dropoff_name, when=None, rules=None, conditions=None):
    """Price of a ride, calculated from the FARE_RULES table, with a line for every charge.
    conditions = current_conditions(...) adds traffic / accident / weather. Without it only the
    time-based rules apply (used for old demo rides and in tests)."""
    a, b = PLACE_BY_NAME.get(pickup_name), PLACE_BY_NAME.get(dropoff_name)
    if not a or not b:
        raise ValueError("Choose pickup and drop-off points from the list")
    if a is b:
        raise ValueError("Pickup and drop-off are the same place")
    when = when or now_local()
    rules = rules or load_fare_rules(get_db())
    on = lambda k: k in rules and rules[k]["active"]

    km = haversine_km(a, b) * ROAD_FACTOR
    lines = []   # what the passenger sees: every part of the price

    def add(key, label, kzt):
        lines.append({"rule": key, "label": label, "kzt": int(round(kzt))})

    add("base", rules["base"]["name"], rules["base"]["amount"])
    add("per_km", f"{round(km, 1)} km x {rules['per_km']['amount']:g} ₸", km * rules["per_km"]["amount"])
    price = rules["base"]["amount"] + km * rules["per_km"]["amount"]

    mountain = a["id"] in ("medeu", "shymbulak") or b["id"] in ("medeu", "shymbulak")
    airport = "airport" in (a["id"], b["id"])
    if mountain and on("mountain"):
        add("mountain", rules["mountain"]["name"], rules["mountain"]["amount"])
        price += rules["mountain"]["amount"]
    if airport and on("airport"):
        add("airport", rules["airport"]["name"], rules["airport"]["amount"])
        price += rules["airport"]["amount"]

    night = when.hour >= 23 or when.hour < 6
    rush = when.weekday() < 5 and (7 <= when.hour < 10 or 17 <= when.hour < 20)
    steps = [("night", night), ("rush", rush)]
    if conditions:
        acc = conditions.get("accident_district") or ""
        steps += [("traffic_moderate", conditions.get("traffic") == "moderate"),
                  ("traffic_heavy", conditions.get("traffic") == "heavy"),
                  ("accident", bool(acc) and acc in (a["district"], b["district"])),
                  ("rain", conditions.get("weather") == "rain"),
                  ("snow", conditions.get("weather") == "snow")]
    total_factor, applied = 1.0, []
    for key, applies in steps:
        if applies and on(key):
            factor = min(rules[key]["amount"], MAX_SURGE / total_factor)   # never more than x2 in total
            if factor <= 1.0:
                continue
            add(key, f"{rules[key]['name']} x{round(factor, 2):g}", price * (factor - 1))
            price *= factor
            total_factor *= factor
            applied.append(key)

    rounded = int(round(price / 10.0)) * 10
    minimum = rules["minimum"]["amount"]
    if rounded < minimum:
        add("minimum", f"{rules['minimum']['name']} {minimum:g} ₸", minimum - sum(l["kzt"] for l in lines))
        rounded = int(minimum)
    elif rounded != sum(l["kzt"] for l in lines):
        lines.append({"rule": None, "label": "Rounded to 10 ₸", "kzt": rounded - sum(l["kzt"] for l in lines)})

    # Travel time: ~28 km/h on free roads; traffic, an accident on the route and bad weather slow it down
    speed = 28.0
    if conditions:
        speed = {"moderate": 21.0, "heavy": 16.0}.get(conditions.get("traffic"), 28.0)
        if acc and acc in (a["district"], b["district"]):
            speed *= 0.85
        speed *= {"rain": 0.9, "snow": 0.75}.get(conditions.get("weather"), 1.0)
    minutes_free = max(5, int(round(km / 28 * 60 + 4)))
    minutes = max(5, int(round(km / speed * 60 + 4)))

    return {
        "distance_km": round(km, 1),
        "minutes": minutes,
        "minutes_free_roads": minutes_free,
        "traffic_delay_min": minutes - minutes_free,
        "price": rounded,
        "lines": lines,
        "night": night and on("night"),
        "rush": rush and on("rush"),
        "mountain": mountain and on("mountain"),
        "airport": airport and on("airport"),
        "extras": applied,
    }



ALMATY_TZ = timezone(timedelta(hours=5))   # Kazakhstan is UTC+5 all year


def now_local():
    """Current time in Almaty. The server (Render) runs in UTC, so a plain datetime.now() is 5 hours behind:
    rush hour and night fare would start at the wrong time."""
    return datetime.now(ALMATY_TZ).replace(tzinfo=None)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def rows(cur):
    return [dict(r) for r in cur.fetchall()]


def init_db(force=False):
    if force and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    fresh = not os.path.exists(DB_PATH)
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        con.executescript(f.read())
    # Migration 007 compatibility: older schema.sql files may not define CONDITIONS.
    # Create it before seed()/insert_default_conditions() so existing databases upgrade safely.
    con.execute("""
        CREATE TABLE IF NOT EXISTS conditions (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT
        )
    """)
    if fresh:
        seed(con)
    else:
        migrate_auth(con)
        migrate_shifts(con)
        insert_default_fares(con)   # migration 005: fills fare_rules once (and the new condition prices)
        insert_default_conditions(con)   # migration 007
    migrate_review_timestamp(con)   # migration 008: original review submission time
    con.commit()
    con.close()


def migrate_auth(con):
    """Upgrade an existing taxi.db: password_hash / ride_rating columns (migration 001),
    drivers.email (migration 002), and give users without a password the demo password."""
    def cols(table):
        return [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
    for table in ("passengers", "drivers"):
        if "password_hash" not in cols(table):
            con.execute(f"ALTER TABLE {table} ADD COLUMN password_hash TEXT")
        con.execute(f"UPDATE {table} SET password_hash=? WHERE password_hash IS NULL OR password_hash=''",
                    (generate_password_hash(DEMO_PASSWORD),))
    if "ride_rating" not in cols("rides"):
        con.execute("ALTER TABLE rides ADD COLUMN ride_rating INTEGER CHECK (ride_rating BETWEEN 1 AND 5)")
    if "ride_comment" not in cols("rides"):
        con.execute("""ALTER TABLE rides ADD COLUMN ride_comment TEXT CHECK (ride_comment IS NULL OR length(ride_comment) <= 1000) """)
    if "feedback_tags" not in cols("rides"):
        con.execute("ALTER TABLE rides ADD COLUMN feedback_tags TEXT")
    if "email" not in cols("drivers"):
        con.execute("ALTER TABLE drivers ADD COLUMN email TEXT")
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_drivers_email ON drivers(email)")
        for phone, mail in DEMO_DRIVER_EMAILS.items():
            con.execute("UPDATE drivers SET email=? WHERE phone=?", (mail, phone))


def migrate_review_timestamp(con):
    """Migration 008: store the original submission time for each ride review."""
    cols = [r[1] for r in con.execute("PRAGMA table_info(rides)")]
    if "rated_at" not in cols:
        con.execute("ALTER TABLE rides ADD COLUMN rated_at TEXT")


def migrate_shifts(con):
    """Migration 004 on an existing taxi.db: schema.sql has just created driver_shifts.
    If it is still empty, put every driver online once, so booking keeps working."""
    if con.execute("SELECT COUNT(*) FROM driver_shifts").fetchone()[0] == 0:
        con.execute("""INSERT INTO driver_shifts(driver_id, started_at)
                       SELECT driver_id, ? FROM drivers""", (now_local().strftime("%Y-%m-%d %H:%M"),))


def seed(con):
    rnd = random.Random(2026)
    insert_default_fares(con)
    insert_default_conditions(con)
    con.row_factory = sqlite3.Row
    fare_rules = load_fare_rules(con)
    passengers = [
        ("Aigerim Seitova", "+7 701 214 55 10", "aigerim.s@mail.kz", "2026-03-02"),
        ("Daniyar Abenov", "+7 705 330 12 87", "daniyar.abenov@gmail.com", "2026-04-15"),
        ("Madina Zhumabayeva", "+7 747 902 44 31", "madina.zh@mail.ru", "2026-05-09"),
        ("Arman Kassymov", "+7 777 118 60 02", "arman.kassymov@gmail.com", "2026-06-21"),
        ("Aliya Nurlanova", "+7 708 645 73 19", "aliya.n@inbox.kz", "2026-07-03"),
        ("Timur Kim", "+7 702 581 09 66", "timur.kim@gmail.com", "2026-08-11"),
        ("Sabina Utegen", "+7 771 403 28 75", "sabina.u@mail.kz", "2026-09-01"),
        ("Yerlan Omarov", "+7 776 290 31 48", "yerlan.o@mail.kz", "2026-09-18"),
    ]
    demo_hash = generate_password_hash(DEMO_PASSWORD)
    con.executemany(
        "INSERT INTO passengers(full_name, phone, email, registration_date, password_hash) VALUES (?,?,?,?,?)",
        [p + (demo_hash,) for p in passengers])

    drivers = [
        ("Bauyrzhan Tulegenov", "+7 701 555 20 11", "bauyrzhan.t@taxi.kz", "AA 0412776", 4.9),
        ("Nursultan Issayev", "+7 707 412 87 30", "nursultan.i@taxi.kz", "AB 1180934", 4.8),
        ("Yerzhan Mussin", "+7 775 300 64 92", "yerzhan.m@taxi.kz", "AA 0938125", 4.7),
        ("Gulnara Akhmetova", "+7 702 909 15 43", "gulnara.a@taxi.kz", "AC 2203418", 4.9),
        ("Ruslan Pak", "+7 747 616 02 58", "ruslan.p@taxi.kz", "AB 0771260", 4.6),
        ("Askhat Baizhanov", "+7 778 140 39 07", "askhat.b@taxi.kz", "AA 1546603", 4.5),
    ]
    con.executemany(
        "INSERT INTO drivers(full_name, phone, email, license_number, rating, password_hash) VALUES (?,?,?,?,?,?)",
        [d + (demo_hash,) for d in drivers])

    # Driver 3 has two cars: the Section 3 example of why CARS is separate
    cars = [
        (1, "512 AKM 02", "Toyota Camry 70", "white"),
        (2, "087 BTR 02", "Hyundai Elantra", "silver"),
        (3, "730 ALM 02", "Chevrolet Cobalt", "white"),
        (3, "264 KZA 02", "Kia K5", "black"),
        (4, "901 MDS 02", "Hyundai Sonata", "blue"),
        (5, "345 NRT 02", "Toyota Corolla", "grey"),
        (6, "618 ZHA 02", "Chevrolet Onix", "white"),
    ]
    con.executemany(
        "INSERT INTO cars(driver_id, plate_number, model, color) VALUES (?,?,?,?)", cars)

    car_ids_by_driver = {}
    for i, c in enumerate(cars, start=1):
        car_ids_by_driver.setdefault(c[0], []).append(i)

    names = [p["name"] for p in PLACES]
    weights = [6 if p["id"] in ("airport", "mega", "esentai", "dostyk", "kbtu", "satbayev", "kaznu", "almaty2")
               else 2 for p in PLACES]
    now = now_local()
    start = now - timedelta(days=58)
    for _ in range(64):
        pickup = rnd.choices(names, weights)[0]
        dropoff = rnd.choices(names, weights)[0]
        while dropoff == pickup:
            dropoff = rnd.choices(names, weights)[0]
        when = start + timedelta(minutes=rnd.randint(0, 56 * 24 * 60))
        when = when.replace(hour=rnd.choice([7, 8, 9, 12, 13, 17, 18, 19, 20, 22]), second=0, microsecond=0)
        if when > now - timedelta(hours=2):
            when = now - timedelta(hours=rnd.randint(3, 48))
        driver_id = rnd.randint(1, 6)
        car_id = rnd.choice(car_ids_by_driver[driver_id])
        q = quote(pickup, dropoff, when, fare_rules)
        status = rnd.choices(["completed", "cancelled"], [10, 1])[0]
        cur = con.execute(
            """INSERT INTO rides(passenger_id, driver_id, car_id, pickup_address, dropoff_address,
                                 start_time, status, price) VALUES (?,?,?,?,?,?,?,?)""",
            (rnd.randint(1, 8), driver_id, car_id, pickup, dropoff,
             when.strftime("%Y-%m-%d %H:%M"), status, q["price"]))
        if status == "completed":
            ride_id = cur.lastrowid
            paid_at = (when + timedelta(minutes=q["minutes"])).strftime("%Y-%m-%d %H:%M")
            method = rnd.choices(["card", "cash"], [3, 2])[0]
            if method == "card" and rnd.random() < 0.08:
                # card failed → later paid in cash (that's why PAYMENTS is a separate table)
                con.execute("""INSERT INTO payments(ride_id, amount, method, payment_status, paid_at)
                               VALUES (?,?,?,?,?)""", (ride_id, q["price"], "card", "failed", paid_at))
                method = "cash"
            con.execute("""INSERT INTO payments(ride_id, amount, method, payment_status, paid_at)
                           VALUES (?,?,?,?,?)""", (ride_id, q["price"], method, "paid", paid_at))

    # Driver shifts: 14 days of history, then drivers 1-5 online now, driver 6 offline
    for driver_id in range(1, 7):
        for days_ago in range(14, 0, -1):
            if rnd.random() < 0.75:
                day = (now - timedelta(days=days_ago)).replace(minute=0, second=0, microsecond=0)
                started = day.replace(hour=rnd.choice([7, 8, 9, 10, 14]))
                ended = started + timedelta(hours=rnd.randint(4, 10))
                con.execute("INSERT INTO driver_shifts(driver_id, started_at, ended_at) VALUES (?,?,?)",
                            (driver_id, started.strftime("%Y-%m-%d %H:%M"), ended.strftime("%Y-%m-%d %H:%M")))
    for driver_id in range(1, 6):
        con.execute("INSERT INTO driver_shifts(driver_id, started_at) VALUES (?,?)",
                    (driver_id, (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M")))

    # Saved places of the demo passenger Aigerim (passenger 1)
    con.executemany("""INSERT INTO saved_places(passenger_id, label, address, icon, created_at)
                       VALUES (1, ?, ?, ?, ?)""",
                    [("Home", "Sairan Lake", "home", "2026-09-01 10:00"),
                     ("University", "KBTU (59 Tole Bi St)", "study", "2026-09-01 10:01"),
                     ("Gym", "Esentai Mall", "heart", "2026-10-12 19:30")])


# ---------------------------------------------------------------------------
# Roles & access control (Section 9)
#
#   passenger: books rides, sees and cancels only their own rides
#   driver:    sees only rides assigned to them, completes them, records payment
#   admin:     sees all tables and reports, adds drivers and cars
#
# Login gives a signed token (no extra table needed, schema stays 5 tables).
# The browser keeps it per tab, so you can open a passenger tab and a driver
# tab side by side.
# ---------------------------------------------------------------------------
from functools import wraps

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SECRET_PATH = os.path.join(BASE_DIR, ".secret")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
TOKEN_MAX_AGE = 12 * 3600  # 12 hours


def _secret():
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    if not os.path.exists(SECRET_PATH):
        with open(SECRET_PATH, "w") as f:
            f.write(os.urandom(24).hex())
    with open(SECRET_PATH) as f:
        return f.read().strip()


signer = URLSafeTimedSerializer(_secret(), salt="minitaxi-auth")


def current_user():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    try:
        return signer.loads(header[7:], max_age=TOKEN_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def require(*roles):
    """Decorator: only these roles may call the endpoint."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            user = current_user()
            if not user:
                return bad("Please log in", 401)
            if user["role"] not in roles:
                return bad("Access denied for role: " + user["role"], 403)
            g.user = user
            return fn(*a, **kw)
        return wrapper
    return deco


def digits(phone):
    return re.sub(r"\D", "", phone or "")



PHONE_RE = re.compile(r"^\+?7[\s\-]?\d{3}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}$")
PLATE_RE = re.compile(r"^\d{3}\s?[A-Z]{3}\s?\d{2}$")


def bad(msg, code=400):
    return jsonify({"error": msg}), code


def body():
    return request.get_json(silent=True) or {}


def now_str():
    return now_local().strftime("%Y-%m-%d %H:%M")


RIDE_SELECT = """
SELECT r.*, p.full_name AS passenger_name, p.phone AS passenger_phone,
       d.full_name AS driver_name, d.phone AS driver_phone, d.rating AS driver_rating,
       c.model AS car_model, c.plate_number, c.color AS car_color,
       (SELECT payment_status FROM payments x WHERE x.ride_id = r.ride_id
          ORDER BY x.payment_id DESC LIMIT 1) AS last_payment_status,
       (SELECT method FROM payments x WHERE x.ride_id = r.ride_id
          ORDER BY x.payment_id DESC LIMIT 1) AS last_payment_method
FROM rides r
JOIN passengers p ON p.passenger_id = r.passenger_id
JOIN drivers d    ON d.driver_id    = r.driver_id
JOIN cars c       ON c.car_id       = r.car_id
"""

def load_owned_ride(ride_id):
    """Return (ride, error). Passengers/drivers may touch only their own rides."""
    ride = get_db().execute("SELECT * FROM rides WHERE ride_id=?", (ride_id,)).fetchone()
    if not ride:
        return None, bad("Ride not found", 404)
    u = g.user
    if u["role"] == "passenger" and ride["passenger_id"] != u["id"]:
        return None, bad("This is not your ride", 403)
    if u["role"] == "driver" and ride["driver_id"] != u["id"]:
        return None, bad("This ride is not assigned to you", 403)
    return ride, None


def has_paid(ride_id):
    return get_db().execute(
        "SELECT 1 FROM payments WHERE ride_id=? AND payment_status='paid'", (ride_id,)).fetchone() is not None



def recalc_driver_rating(driver_id, commit=True):
    """drivers.rating = average of the driver's ride ratings (one decimal)."""
    db = get_db()
    db.execute("""
        UPDATE drivers
        SET rating = COALESCE(
            (SELECT ROUND(AVG(ride_rating), 1)
             FROM rides
             WHERE rides.driver_id = drivers.driver_id
               AND ride_rating IS NOT NULL),
            rating)
        WHERE driver_id = ?""", (driver_id,))
    if commit:
        db.commit()
    
@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/places")
def api_places():
    return jsonify(PLACES)


@app.post("/api/quote")
def api_quote():
    b = body()
    try:
        return jsonify(quote(b.get("pickup"), b.get("dropoff"), conditions=current_conditions(get_db())))
    except ValueError as e:
        return bad(str(e))


@app.get("/api/demo-accounts")
def demo_accounts():
    """Demo only: a few accounts to click on the login screen."""
    db = get_db()
    return jsonify({
        "passengers": rows(db.execute("SELECT full_name, phone, email FROM passengers ORDER BY passenger_id LIMIT 3")),
        "drivers": rows(db.execute("SELECT full_name, phone, email FROM drivers ORDER BY driver_id LIMIT 3")),
        "admin_hint": ADMIN_PASSWORD if ADMIN_PASSWORD == "admin123" else None,
        "demo_password": DEMO_PASSWORD,
    })


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def issue(role, uid, name):
    token = signer.dumps({"role": role, "id": uid, "name": name})
    return jsonify({"token": token, "role": role, "id": uid, "name": name})


@app.post("/api/login")
def login():
    b = body()
    role = b.get("role")
    db = get_db()
    if role == "admin":
        if b.get("password") != ADMIN_PASSWORD:
            return bad("Wrong admin password", 401)
        return issue("admin", 0, "Admin")
    if role not in ("passenger", "driver"):
        return bad("Unknown role")
    table, key = ("passengers", "passenger_id") if role == "passenger" else ("drivers", "driver_id")
    ident = (b.get("login") or b.get("phone") or "").strip()
    password = b.get("password") or ""
    if not ident:
        return bad("Enter your email or phone number")
    if not password:
        return bad("Enter your password")
    if "@" in ident:
        r = db.execute(f"SELECT {key} AS id, full_name, password_hash FROM {table} WHERE lower(email)=lower(?)",
                       (ident,)).fetchone()
    else:
        want, r = digits(ident), None
        if len(want) >= 10:
            for row in db.execute(f"SELECT {key} AS id, full_name, phone, password_hash FROM {table}"):
                if digits(row["phone"])[-10:] == want[-10:]:
                    r = row
                    break
    if r and r["password_hash"] and check_password_hash(r["password_hash"], password):
        return issue(role, r["id"], r["full_name"])
    # same message for "no such user" and "wrong password": do not reveal which accounts exist
    return bad("Wrong email/phone or password", 401)


@app.post("/api/signup")
def signup():
    """A new passenger registers (row in PASSENGERS) and is logged in."""
    b = body()
    err = validate_passenger(b)
    if err:
        return err
    try:
        cur = get_db().execute(
            "INSERT INTO passengers(full_name, phone, email, registration_date, password_hash) VALUES (?,?,?,date('now'),?)",
            (b["full_name"].strip(), b["phone"].strip(), (b.get("email") or "").strip() or None,
             generate_password_hash(b["password"])))
        get_db().commit()
    except sqlite3.IntegrityError:
        return bad("A passenger with this phone or email already exists", 409)
    return issue("passenger", cur.lastrowid, b["full_name"].strip())


@app.get("/api/me")
@require("passenger", "driver", "admin")
def me():
    u, db = g.user, get_db()
    out = dict(u)
    if u["role"] == "passenger":
        p = db.execute("SELECT * FROM passengers WHERE passenger_id=?", (u["id"],)).fetchone()
        if not p:
            return bad("Account no longer exists", 401)
        out["profile"] = {k: v for k, v in dict(p).items() if k != "password_hash"}
        out["stats"] = dict(db.execute("""
            SELECT COUNT(*) AS rides,
                   COALESCE(SUM(CASE WHEN status='completed' THEN price END),0) AS spent
            FROM rides WHERE passenger_id=?""", (u["id"],)).fetchone())
    elif u["role"] == "driver":
        d = db.execute("SELECT * FROM drivers WHERE driver_id=?", (u["id"],)).fetchone()
        if not d:
            return bad("Account no longer exists", 401)
        out["profile"] = {k: v for k, v in dict(d).items() if k != "password_hash"}
        out["cars"] = rows(db.execute("SELECT * FROM cars WHERE driver_id=? ORDER BY car_id", (u["id"],)))
        shift = open_shift(u["id"])
        out["online"] = shift is not None
        out["online_since"] = shift["started_at"] if shift else None
    return jsonify(out)


def validate_review_payload(b):
    """Validate and normalize a review payload for both create and edit."""
    raw = b.get("rating")
    if isinstance(raw, bool) or not isinstance(raw, (int, str)) or not str(raw).strip().isdigit():
        return None, bad("Rating must be a whole number from 1 to 5")

    rating = int(raw)
    if not 1 <= rating <= 5:
        return None, bad("Rating must be a whole number from 1 to 5")

    comment = b.get("comment", "")
    if comment is None:
        comment = ""
    if not isinstance(comment, str):
        return None, bad("Comment must be text")
    comment = comment.strip()
    if len(comment) > 1000:
        return None, bad("Comment must not exceed 1000 characters")

    raw_tags = b.get("feedback_tags", [])
    if raw_tags is None:
        raw_tags = []
    if not isinstance(raw_tags, list) or any(not isinstance(tag, str) for tag in raw_tags):
        return None, bad("Feedback options must be a list of text values")
    tags = list(dict.fromkeys(tag.strip() for tag in raw_tags if tag.strip()))
    allowed_tags = IMPROVEMENT_FEEDBACK_OPTIONS if rating <= 3 else POSITIVE_FEEDBACK_OPTIONS
    if any(tag not in allowed_tags for tag in tags):
        return None, bad("One or more feedback options are not valid for this rating")
    if rating <= 3 and not tags and not comment:
        return None, bad("Select at least one feedback option or leave a comment")

    return {"rating": rating, "comment": comment, "tags": tags}, None


def review_response(ride_id, rating, comment, tags, driver_id):
    driver_rating = get_db().execute(
        "SELECT rating FROM drivers WHERE driver_id=?", (driver_id,)
    ).fetchone()[0]
    return jsonify({
        "ride_id": ride_id,
        "ride_rating": rating,
        "ride_comment": comment or None,
        "feedback_tags": tags,
        "driver_rating": driver_rating
    })


# ---------------------------------------------------------------------------
# PASSENGER
# ---------------------------------------------------------------------------
SAVED_ICONS = ("home", "work", "study", "heart", "pin")
MAX_SAVED_PLACES = 10


@app.get("/api/my/places")
@require("passenger")
def my_places():
    """The passenger's saved places. With ?from=<place> each one also gets the price and the
    travel time from there right now, including traffic, accidents and weather."""
    db, pid = get_db(), g.user["id"]
    places = rows(db.execute(
        "SELECT place_id, label, address, icon FROM saved_places WHERE passenger_id=? ORDER BY place_id", (pid,)))
    origin = request.args.get("from")
    if origin in PLACE_BY_NAME:
        cond = current_conditions(db)
        rules = load_fare_rules(db)
        for p in places:
            if p["address"] == origin:
                p["estimate"] = None          # the passenger is already there
                continue
            q = quote(origin, p["address"], rules=rules, conditions=cond)
            p["estimate"] = {"price": q["price"], "minutes": q["minutes"],
                             "traffic_delay_min": q["traffic_delay_min"], "extras": q["extras"]}
        return jsonify({"from": origin, "traffic": cond["traffic"], "places": places})
    return jsonify({"from": None, "places": places})


@app.post("/api/my/places")
@require("passenger")
def add_place():
    """Save a new favourite place. The database refuses a second place with the same name."""
    db, pid, b = get_db(), g.user["id"], body()
    label = (b.get("label") or "").strip()
    address, icon = b.get("address"), b.get("icon") or "pin"
    if not 1 <= len(label) <= 30:
        return bad("Give the place a name, up to 30 characters")
    if address not in PLACE_BY_NAME:
        return bad("Choose the address from the list")
    if icon not in SAVED_ICONS:
        return bad("Unknown icon")
    if db.execute("SELECT COUNT(*) FROM saved_places WHERE passenger_id=?", (pid,)).fetchone()[0] >= MAX_SAVED_PLACES:
        return bad(f"You can save up to {MAX_SAVED_PLACES} places", 409)
    try:
        cur = db.execute("""INSERT INTO saved_places(passenger_id, label, address, icon, created_at)
                            VALUES (?,?,?,?,?)""", (pid, label, address, icon, now_str()))
        db.commit()
    except sqlite3.IntegrityError:
        return bad(f'You already have a place called "{label}"', 409)
    return jsonify({"place_id": cur.lastrowid, "label": label, "address": address, "icon": icon}), 201


@app.delete("/api/my/places/<int:place_id>")
@require("passenger")
def delete_place(place_id):
    """Delete one of your own saved places (someone else's place: 404)."""
    db = get_db()
    cur = db.execute("DELETE FROM saved_places WHERE place_id=? AND passenger_id=?", (place_id, g.user["id"]))
    db.commit()
    if cur.rowcount == 0:
        return bad("Place not found", 404)
    return jsonify({"deleted": place_id})


@app.get("/api/my/rides")
@require("passenger")
def my_rides():
    return jsonify(rows(get_db().execute(
        RIDE_SELECT + " WHERE r.passenger_id=? ORDER BY (r.status='requested') DESC, r.start_time DESC",
        (g.user["id"],))))


@app.post("/api/rides")
@require("passenger")
def book_ride():
    """Main action of the system: a passenger books a ride."""
    b, db, pid = body(), get_db(), g.user["id"]
    if db.execute("SELECT 1 FROM rides WHERE passenger_id=? AND status='requested'", (pid,)).fetchone():
        return bad("You already have an active ride", 409)
    try:
        q = quote(b.get("pickup"), b.get("dropoff"), conditions=current_conditions(db))
    except ValueError as e:
        return bad(str(e))
    # an online, free driver with a car, highest rating first
    pick = db.execute("""
        SELECT d.driver_id, c.car_id FROM drivers d
        JOIN cars c ON c.driver_id = d.driver_id
        WHERE NOT EXISTS (SELECT 1 FROM rides r WHERE r.driver_id=d.driver_id AND r.status='requested')
          AND EXISTS (SELECT 1 FROM driver_shifts s WHERE s.driver_id=d.driver_id AND s.ended_at IS NULL)
        ORDER BY d.rating DESC, RANDOM() LIMIT 1""").fetchone()
    if not pick:
        return bad("All drivers are busy or offline right now. Please try again in a few minutes.", 409)
    cur = db.execute("""INSERT INTO rides(passenger_id, driver_id, car_id, pickup_address, dropoff_address,
                                          start_time, status, price)
                        VALUES (?,?,?,?,?,?, 'requested', ?)""",
                     (pid, pick["driver_id"], pick["car_id"], b["pickup"], b["dropoff"], now_str(), q["price"]))
    db.commit()
    ride = db.execute(RIDE_SELECT + " WHERE r.ride_id=?", (cur.lastrowid,)).fetchone()
    return jsonify({**dict(ride), "quote": q}), 201


@app.post("/api/rides/<int:ride_id>/cancel")
@require("passenger", "admin")
def cancel_ride(ride_id):
    ride, err = load_owned_ride(ride_id)
    if err:
        return err
    if ride["status"] != "requested":
        return bad("Only an active ride can be cancelled", 409)
    get_db().execute("UPDATE rides SET status='cancelled' WHERE ride_id=?", (ride_id,))
    get_db().commit()
    return jsonify({"ride_id": ride_id, "status": "cancelled"})

@app.post("/api/rides/<int:ride_id>/rate")
@require("passenger")
def rate_ride(ride_id):
    """Create the initial review for a completed ride."""
    payload, err = validate_review_payload(body())
    if err:
        return err

    ride, err = load_owned_ride(ride_id)
    if err:
        return err
    if ride["status"] != "completed":
        return bad("Only a completed ride can be rated", 409)
    if ride["ride_rating"] is not None:
        return bad("This ride is already rated", 409)

    db = get_db()
    # Use the app's Almaty-local clock, not the server's UTC clock.
    rated_at = now_local().isoformat(timespec="seconds")
    try:
        db.execute("BEGIN")
        cur = db.execute("""
            UPDATE rides
            SET ride_rating=?, ride_comment=?, feedback_tags=?, rated_at=?
            WHERE ride_id=? AND ride_rating IS NULL
        """, (
            payload["rating"], payload["comment"] or None,
            json.dumps(payload["tags"], ensure_ascii=False) if payload["tags"] else None,
            rated_at, ride_id
        ))
        if cur.rowcount != 1:
            db.rollback()
            return bad("This ride is already rated", 409)
        recalc_driver_rating(ride["driver_id"], commit=False)
        db.commit()
    except sqlite3.Error:
        db.rollback()
        return bad("Transaction error, changes rolled back", 500)

    return review_response(ride_id, payload["rating"], payload["comment"],
                           payload["tags"], ride["driver_id"])


@app.put("/api/rides/<int:ride_id>/rate")
@require("passenger")
def edit_ride_review(ride_id):
    """Edit a review repeatedly, but only within one hour of its first submission."""
    payload, err = validate_review_payload(body())
    if err:
        return err

    ride, err = load_owned_ride(ride_id)
    if err:
        return err
    if ride["status"] != "completed":
        return bad("Only a completed ride can be reviewed", 409)
    if ride["ride_rating"] is None:
        return bad("This ride has not been rated yet", 409)
    if not ride["rated_at"]:
        return bad("This review cannot be edited because its original submission time is unavailable", 409)

    try:
        original_time = datetime.fromisoformat(ride["rated_at"])
    except (TypeError, ValueError):
        return bad("The original review timestamp is invalid", 409)

    if now_local() >= original_time + timedelta(hours=1):
        return bad("The one-hour review editing period has expired", 409)

    db = get_db()
    try:
        db.execute("BEGIN")
        cur = db.execute("""
            UPDATE rides
            SET ride_rating=?, ride_comment=?, feedback_tags=?
            WHERE ride_id=? AND ride_rating IS NOT NULL AND rated_at=?
        """, (
            payload["rating"], payload["comment"] or None,
            json.dumps(payload["tags"], ensure_ascii=False) if payload["tags"] else None,
            ride_id, ride["rated_at"]
        ))
        if cur.rowcount != 1:
            db.rollback()
            return bad("The review could not be updated", 409)
        recalc_driver_rating(ride["driver_id"], commit=False)
        db.commit()
    except sqlite3.Error:
        db.rollback()
        return bad("Transaction error, changes rolled back", 500)

    # Keep rated_at unchanged: editing never extends the original one-hour window.
    return review_response(ride_id, payload["rating"], payload["comment"],
                           payload["tags"], ride["driver_id"])


# ---------------------------------------------------------------------------
# DRIVER
# ---------------------------------------------------------------------------
def open_shift(driver_id):
    """The driver's current shift, or None if the driver is offline."""
    return get_db().execute(
        "SELECT * FROM driver_shifts WHERE driver_id=? AND ended_at IS NULL", (driver_id,)).fetchone()


@app.post("/api/driver/online")
@require("driver")
def go_online():
    """Driver starts a shift: a new row in DRIVER_SHIFTS with no ended_at."""
    did = g.user["id"]
    if open_shift(did):
        return bad("You are already online", 409)
    get_db().execute("INSERT INTO driver_shifts(driver_id, started_at) VALUES (?,?)", (did, now_str()))
    get_db().commit()
    return jsonify({"online": True})


@app.post("/api/driver/offline")
@require("driver")
def go_offline():
    """Driver ends the shift: ended_at gets the current time."""
    did, db = g.user["id"], get_db()
    shift = open_shift(did)
    if not shift:
        return bad("You are already offline", 409)
    if db.execute("SELECT 1 FROM rides WHERE driver_id=? AND status='requested'", (did,)).fetchone():
        return bad("Finish your current ride before going offline", 409)
    db.execute("UPDATE driver_shifts SET ended_at=? WHERE shift_id=?", (now_str(), shift["shift_id"]))
    db.commit()
    return jsonify({"online": False})


@app.get("/api/driver/rides")
@require("driver")
def driver_rides():
    data = rows(get_db().execute(
        RIDE_SELECT + " WHERE r.driver_id=? ORDER BY (r.status='requested') DESC, r.start_time DESC LIMIT 200",
        (g.user["id"],)))
    for r in data:
        if r["status"] != "requested":      # passenger phone only while the ride is active
            r["passenger_phone"] = None
        r.pop("driver_phone", None)
    return jsonify(data)


@app.get("/api/driver/earnings")
@require("driver")
def driver_earnings():
    db, did = get_db(), g.user["id"]
    monthly = rows(db.execute("""
        SELECT strftime('%Y-%m', p.paid_at) AS month, COUNT(DISTINCT r.ride_id) AS rides, SUM(p.amount) AS earnings_kzt
        FROM payments p JOIN rides r ON r.ride_id = p.ride_id
        WHERE p.payment_status='paid' AND r.driver_id=?
        GROUP BY month ORDER BY month DESC""", (did,)))
    # place among all drivers this month (no other drivers' names or money shown)
    month = now_local().strftime("%Y-%m")
    ranking = [r[0] for r in db.execute("""
        SELECT r.driver_id FROM payments p JOIN rides r ON r.ride_id=p.ride_id
        WHERE p.payment_status='paid' AND strftime('%Y-%m', p.paid_at)=?
        GROUP BY r.driver_id ORDER BY SUM(p.amount) DESC""", (month,))]
    place = ranking.index(did) + 1 if did in ranking else None
    total_drivers = db.execute("SELECT COUNT(*) FROM drivers").fetchone()[0]
    return jsonify({"monthly": monthly, "month": month, "place": place, "total_drivers": total_drivers})


@app.post("/api/rides/<int:ride_id>/complete")
@require("driver")
def complete_ride(ride_id):
    """Complete the ride + payment in one transaction (Section 9)."""
    b = body()
    method = b.get("method")
    if method not in ("cash", "card"):
        return bad("Payment method must be cash or card")
    ride, err = load_owned_ride(ride_id)
    if err:
        return err
    if ride["status"] != "requested":
        return bad("Only an active ride can be completed", 409)
    status = "failed" if (method == "card" and b.get("simulate_fail")) else "paid"
    db = get_db()
    try:
        db.execute("BEGIN")
        db.execute("UPDATE rides SET status='completed' WHERE ride_id=?", (ride_id,))
        db.execute("""INSERT INTO payments(ride_id, amount, method, payment_status, paid_at)
                      VALUES (?,?,?,?,?)""", (ride_id, ride["price"], method, status, now_str()))
        db.commit()
    except sqlite3.Error:
        db.rollback()
        return bad("Transaction error, changes rolled back", 500)
    return jsonify({"ride_id": ride_id, "payment_status": status})


@app.post("/api/rides/<int:ride_id>/pay")
@require("passenger", "driver")
def retry_payment(ride_id):
    """Card failed earlier: passenger pays again by card, or driver takes cash."""
    ride, err = load_owned_ride(ride_id)
    if err:
        return err
    method = "card" if g.user["role"] == "passenger" else "cash"
    if ride["status"] != "completed":
        return bad("Only a completed ride can be paid", 409)
    if has_paid(ride_id):
        return bad("This ride is already paid", 409)
    get_db().execute("""INSERT INTO payments(ride_id, amount, method, payment_status, paid_at)
                        VALUES (?,?,?, 'paid', ?)""", (ride_id, ride["price"], method, now_str()))
    get_db().commit()
    return jsonify({"ride_id": ride_id, "payment_status": "paid", "method": method})


# ---------------------------------------------------------------------------
# ADMIN
# ---------------------------------------------------------------------------
@app.get("/api/stats")
@require("admin")
def api_stats():
    db = get_db()
    one = lambda sql: db.execute(sql).fetchone()[0]
    month = now_local().strftime("%Y-%m")
    return jsonify({
        "passengers": one("SELECT COUNT(*) FROM passengers"),
        "drivers": one("SELECT COUNT(*) FROM drivers"),
        "cars": one("SELECT COUNT(*) FROM cars"),
        "rides": one("SELECT COUNT(*) FROM rides"),
        "payments": one("SELECT COUNT(*) FROM payments"),
        "active_rides": one("SELECT COUNT(*) FROM rides WHERE status='requested'"),
        "free_drivers": one("""SELECT COUNT(*) FROM drivers d WHERE EXISTS (SELECT 1 FROM cars c WHERE c.driver_id=d.driver_id)
                               AND NOT EXISTS (SELECT 1 FROM rides r WHERE r.driver_id=d.driver_id AND r.status='requested')
                               AND EXISTS (SELECT 1 FROM driver_shifts s WHERE s.driver_id=d.driver_id AND s.ended_at IS NULL)"""),
        "online_drivers": one("SELECT COUNT(*) FROM driver_shifts WHERE ended_at IS NULL"),
        "month_revenue": db.execute(
            "SELECT COALESCE(SUM(amount),0) FROM payments WHERE payment_status='paid' AND strftime('%Y-%m',paid_at)=?",
            (month,)).fetchone()[0],
        "month": month,
    })


def validate_passenger(b):
    name, phone, email = (b.get("full_name") or "").strip(), (b.get("phone") or "").strip(), (b.get("email") or "").strip()
    if len(name) < 2:
        return bad("Enter the passenger's name")
    if not PHONE_RE.match(phone):
        return bad("Phone format: +7 7XX XXX XX XX")
    if not email or "@" not in email:
        return bad("Enter a valid email")
    if len(b.get("password") or "") < MIN_PASSWORD_LEN:
        return bad(f"Password must be at least {MIN_PASSWORD_LEN} characters")
    return None


@app.get("/api/passengers")
@require("admin")
def list_passengers():
    return jsonify(rows(get_db().execute("""
        SELECT p.passenger_id, p.full_name, p.phone, p.email, p.registration_date,
               (p.password_hash IS NOT NULL AND p.password_hash != '') AS password_hash,
               (SELECT COUNT(*) FROM rides r WHERE r.passenger_id=p.passenger_id) AS rides_count
        FROM passengers p ORDER BY p.passenger_id""")))


@app.post("/api/passengers")
@require("admin")
def add_passenger():
    b = body()
    err = validate_passenger(b)
    if err:
        return err
    try:
        cur = get_db().execute(
            "INSERT INTO passengers(full_name, phone, email, registration_date, password_hash) VALUES (?,?,?,date('now'),?)",
            (b["full_name"].strip(), b["phone"].strip(), (b.get("email") or "").strip() or None,
             generate_password_hash(b["password"])))
        get_db().commit()
    except sqlite3.IntegrityError:
        return bad("A passenger with this phone or email already exists", 409)
    return jsonify({"passenger_id": cur.lastrowid}), 201


@app.get("/api/drivers")
@require("admin")
def list_drivers():
    return jsonify(rows(get_db().execute("""
        SELECT d.driver_id, d.full_name, d.phone, d.email, d.license_number, d.rating,
               (d.password_hash IS NOT NULL AND d.password_hash != '') AS password_hash,
          (SELECT COUNT(*) FROM cars c WHERE c.driver_id=d.driver_id) AS cars_count,
          (SELECT COUNT(*) FROM rides r WHERE r.driver_id=d.driver_id AND r.status='completed') AS rides_done,
          EXISTS (SELECT 1 FROM rides r WHERE r.driver_id=d.driver_id AND r.status='requested') AS busy
        FROM drivers d ORDER BY d.driver_id""")))


@app.post("/api/drivers")
@require("admin")
def add_driver():
    b = body()
    name, phone, lic = (b.get("full_name") or "").strip(), (b.get("phone") or "").strip(), (b.get("license_number") or "").strip().upper()
    email = (b.get("email") or "").strip()
    try:
        rating = float(b.get("rating") or 5)
    except ValueError:
        return bad("Rating must be a number from 1 to 5")
    if len(name) < 2:
        return bad("Enter the driver's name")
    if not PHONE_RE.match(phone):
        return bad("Phone format: +7 7XX XXX XX XX")
    if not email or "@" not in email:
        return bad("Enter a valid email")
    if len(lic) < 5:
        return bad("Enter the driving license number")
    if not 1 <= rating <= 5:
        return bad("Rating must be a number from 1 to 5")
    if len(b.get("password") or "") < MIN_PASSWORD_LEN:
        return bad(f"Password must be at least {MIN_PASSWORD_LEN} characters")
    try:
        cur = get_db().execute(
            "INSERT INTO drivers(full_name, phone, email, license_number, rating, password_hash) VALUES (?,?,?,?,?,?)",
            (name, phone, email, lic, rating, generate_password_hash(b["password"])))
        get_db().commit()
    except sqlite3.IntegrityError:
        return bad("A driver with this phone, email or license already exists", 409)
    return jsonify({"driver_id": cur.lastrowid}), 201


@app.get("/api/cars")
@require("admin")
def list_cars():
    return jsonify(rows(get_db().execute("""
        SELECT c.*, d.full_name AS driver_name FROM cars c
        JOIN drivers d ON d.driver_id=c.driver_id ORDER BY c.car_id""")))


@app.post("/api/cars")
@require("admin")
def add_car():
    b = body()
    plate = re.sub(r"\s+", " ", (b.get("plate_number") or "").strip().upper())
    model, color = (b.get("model") or "").strip(), (b.get("color") or "").strip()
    if not PLATE_RE.match(plate):
        return bad("Plate format: 123 ABC 02")
    if len(model) < 2:
        return bad("Enter the car model")
    try:
        cur = get_db().execute(
            "INSERT INTO cars(driver_id, plate_number, model, color) VALUES (?,?,?,?)",
            (b.get("driver_id"), plate, model, color or None))
        get_db().commit()
    except sqlite3.IntegrityError as e:
        if "FOREIGN KEY" in str(e) or "NOT NULL" in str(e):
            return bad("This driver does not exist (driver_id → DRIVERS)", 422)
        return bad("A car with this plate already exists", 409)
    return jsonify({"car_id": cur.lastrowid}), 201


@app.get("/api/rides")
@require("admin")
def list_rides():
    sql, args, where = RIDE_SELECT, [], []
    if request.args.get("status"):
        where.append("r.status = ?"); args.append(request.args["status"])
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY (r.status='requested') DESC, r.start_time DESC LIMIT ?"
    args.append(int(request.args.get("limit", 200)))
    return jsonify(rows(get_db().execute(sql, args)))


@app.get("/api/payments")
@require("admin")
def list_payments():
    return jsonify(rows(get_db().execute("""
        SELECT p.*, r.passenger_id, r.driver_id FROM payments p
        JOIN rides r ON r.ride_id=p.ride_id ORDER BY p.payment_id DESC LIMIT 300""")))


EARNINGS_SQL = """SELECT d.driver_id,
       d.full_name,
       strftime('%Y-%m', p.paid_at) AS month,
       COUNT(DISTINCT r.ride_id)    AS rides,
       SUM(p.amount)                AS earnings_kzt
FROM payments p
JOIN rides   r ON r.ride_id   = p.ride_id
JOIN drivers d ON d.driver_id = r.driver_id
WHERE p.payment_status = 'paid'
  AND strftime('%Y-%m', p.paid_at) = :month
GROUP BY d.driver_id
ORDER BY earnings_kzt DESC;"""


@app.get("/api/reports/driver-earnings")
@require("admin")
def report_earnings():
    db = get_db()
    months = [r[0] for r in db.execute(
        "SELECT DISTINCT strftime('%Y-%m', paid_at) m FROM payments WHERE payment_status='paid' ORDER BY m DESC")]
    month = request.args.get("month") or (months[0] if months else now_local().strftime("%Y-%m"))
    data = rows(db.execute(EARNINGS_SQL, {"month": month}))
    places = rows(db.execute("""SELECT pickup_address AS place, COUNT(*) AS rides FROM rides
                                GROUP BY pickup_address ORDER BY rides DESC LIMIT 6"""))
    methods = rows(db.execute("""SELECT method, COUNT(*) AS n, SUM(amount) AS total FROM payments
                                 WHERE payment_status='paid' GROUP BY method"""))
    unpaid = rows(db.execute("""SELECT r.ride_id, r.price FROM rides r WHERE r.status='completed'
                                AND NOT EXISTS (SELECT 1 FROM payments p WHERE p.ride_id=r.ride_id
                                                AND p.payment_status='paid')"""))
    return jsonify({"month": month, "months": months, "sql": EARNINGS_SQL, "rows": data,
                    "top_pickups": places, "methods": methods, "unpaid": unpaid})


@app.get("/api/driver_shifts")
@require("admin")
def list_shifts():
    return jsonify(rows(get_db().execute(
        "SELECT * FROM driver_shifts ORDER BY (ended_at IS NULL) DESC, started_at DESC LIMIT 300")))


HOURS_SQL = """SELECT d.driver_id,
       d.full_name,
       COUNT(s.shift_id) AS shifts,
       ROUND(SUM(julianday(COALESCE(s.ended_at, :now)) - julianday(s.started_at)) * 24, 1) AS hours
FROM driver_shifts s
JOIN drivers d ON d.driver_id = s.driver_id
WHERE s.started_at >= :since
GROUP BY d.driver_id
ORDER BY hours DESC;"""


@app.get("/api/reports/driver-hours")
@require("admin")
def report_hours():
    """Hours online per driver over the last 7 days (an open shift counts until now)."""
    since = (now_local() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M")
    data = rows(get_db().execute(HOURS_SQL, {"now": now_str(), "since": since}))
    return jsonify({"since": since, "sql": HOURS_SQL, "rows": data})


@app.get("/api/conditions")
def get_conditions():
    """Traffic, accident and weather right now (public: the map shows them to everybody)."""
    db = get_db()
    c = current_conditions(db)
    c["districts"] = DISTRICTS
    c["rates"] = {r["rule_key"]: r["amount"] for r in db.execute(
        "SELECT rule_key, amount FROM fare_rules WHERE active=1 AND rule_key IN "
        "('traffic_moderate','traffic_heavy','accident','rain','snow')")}
    return jsonify(c)


@app.post("/api/conditions")
@require("admin")
def set_conditions():
    """Admin sets the traffic, the district with an accident and the weather mode."""
    db, b = get_db(), body()
    new = {}
    if "traffic" in b:
        if b["traffic"] not in TRAFFIC_LEVELS:
            return bad("Traffic must be free, moderate or heavy")
        new["traffic"] = b["traffic"]
    if "accident_district" in b:
        if b["accident_district"] not in ("",) + tuple(DISTRICTS):
            return bad("Unknown district")
        new["accident_district"] = b["accident_district"]
    if "weather_mode" in b:
        if b["weather_mode"] not in WEATHER_MODES:
            return bad("Weather must be auto, clear, rain or snow")
        new["weather_mode"] = b["weather_mode"]
    for k, v in new.items():
        db.execute("INSERT INTO conditions(key, value, updated_at) VALUES (?,?,?) "
                   "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                   (k, v, now_str()))
    db.commit()
    return get_conditions()


@app.get("/api/saved_places")
@require("admin")
def list_saved_places():
    return jsonify(rows(get_db().execute("SELECT * FROM saved_places ORDER BY place_id")))


@app.get("/api/fares")
def public_fares():
    """All active prices, for the passenger's price panel (no login needed)."""
    return jsonify(rows(get_db().execute(
        "SELECT rule_key, name, kind, amount, applies_to FROM fare_rules WHERE active=1 ORDER BY rowid")))


@app.get("/api/fare_rules")
@require("admin")
def list_fare_rules():
    return jsonify(rows(get_db().execute("SELECT * FROM fare_rules ORDER BY rowid")))


@app.post("/api/fare_rules/<rule_key>")
@require("admin")
def update_fare_rule(rule_key):
    """Admin changes a price or switches an extra charge on/off. New bookings use it at once;
    rides already booked keep the price saved in rides.price."""
    db, b = get_db(), body()
    rule = db.execute("SELECT * FROM fare_rules WHERE rule_key=?", (rule_key,)).fetchone()
    if not rule:
        return bad("No such price rule", 404)
    try:
        amount = float(b.get("amount", rule["amount"]))
    except (TypeError, ValueError):
        return bad("The amount must be a number")
    active = 1 if b.get("active", rule["active"]) in (1, True, "1", "true") else 0
    if rule_key in CORE_RULES and not active:
        return bad("Base fare, price per km and minimum fare cannot be switched off")
    if rule["kind"] == "multiplier" and not 1 <= amount <= 3:
        return bad("A multiplier must be between 1 and 3")
    if amount <= 0:
        return bad("The amount must be more than 0")
    if rule["kind"] != "multiplier" and amount > 100000:
        return bad("The amount is too large")
    db.execute("UPDATE fare_rules SET amount=?, active=?, updated_at=? WHERE rule_key=?",
               (amount, active, now_str(), rule_key))
    db.commit()
    return jsonify(dict(db.execute("SELECT * FROM fare_rules WHERE rule_key=?", (rule_key,)).fetchone()))


@app.post("/api/reset")
@require("admin")
def api_reset():
    close_db(None)
    init_db(force=True)
    return jsonify({"ok": True})


init_db()

if __name__ == "__main__":
    # Local run: python app.py. On a server we use gunicorn instead (see README, "Deploy").
    app.run(debug=os.environ.get("FLASK_DEBUG", "1") == "1", port=int(os.environ.get("PORT", 5000)))