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
import math
import os
import random
import re
import sqlite3
from datetime import datetime, timedelta

from flask import Flask, g, jsonify, request, send_from_directory
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "taxi.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")

DEMO_PASSWORD = "demo123"  # password of all demo passengers and drivers
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
BASE_FARE = 500
PER_KM = 140
MIN_FARE = 800
ROAD_FACTOR = 1.35          # roads are longer than a straight line
MOUNTAIN_SURCHARGE = 600    # Medeu / Shymbulak are up in the mountains
NIGHT_FACTOR = 1.2          # 23:00–06:00


def haversine_km(a, b):
    r = 6371.0
    dlat = math.radians(b["lat"] - a["lat"])
    dlng = math.radians(b["lng"] - a["lng"])
    h = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(a["lat"])) * math.cos(math.radians(b["lat"])) * math.sin(dlng / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(h))


def quote(pickup_name, dropoff_name, when=None):
    a, b = PLACE_BY_NAME.get(pickup_name), PLACE_BY_NAME.get(dropoff_name)
    if not a or not b:
        raise ValueError("Choose pickup and drop-off points from the list")
    if a is b:
        raise ValueError("Pickup and drop-off are the same place")
    when = when or datetime.now()
    km = haversine_km(a, b) * ROAD_FACTOR
    price = BASE_FARE + PER_KM * km
    mountain = a["id"] in ("medeu", "shymbulak") or b["id"] in ("medeu", "shymbulak")
    if mountain:
        price += MOUNTAIN_SURCHARGE
    night = when.hour >= 23 or when.hour < 6
    if night:
        price *= NIGHT_FACTOR
    price = max(MIN_FARE, int(round(price / 10.0)) * 10)
    return {
        "distance_km": round(km, 1),
        "minutes": max(5, int(round(km / 28 * 60 + 4))),  # ~28 km/h in the city
        "price": price,
        "night": night,
        "mountain": mountain,
    }



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
    if fresh:
        seed(con)
    else:
        migrate_auth(con)
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
    if "email" not in cols("drivers"):
        con.execute("ALTER TABLE drivers ADD COLUMN email TEXT")
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_drivers_email ON drivers(email)")
        for phone, mail in DEMO_DRIVER_EMAILS.items():
            con.execute("UPDATE drivers SET email=? WHERE phone=?", (mail, phone))


def seed(con):
    rnd = random.Random(2026)
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
    now = datetime.now()
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
        q = quote(pickup, dropoff, when)
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
    return datetime.now().strftime("%Y-%m-%d %H:%M")


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
        return jsonify(quote(b.get("pickup"), b.get("dropoff")))
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
    return jsonify(out)


# ---------------------------------------------------------------------------
# PASSENGER
# ---------------------------------------------------------------------------
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
        q = quote(b.get("pickup"), b.get("dropoff"))
    except ValueError as e:
        return bad(str(e))
    # a free driver with a car, highest rating first
    pick = db.execute("""
        SELECT d.driver_id, c.car_id FROM drivers d
        JOIN cars c ON c.driver_id = d.driver_id
        WHERE NOT EXISTS (SELECT 1 FROM rides r WHERE r.driver_id=d.driver_id AND r.status='requested')
        ORDER BY d.rating DESC, RANDOM() LIMIT 1""").fetchone()
    if not pick:
        return bad("All drivers are busy right now. Please try again in a few minutes.", 409)
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
    """Passenger rates a completed ride and optionally leaves a comment."""

    b = body()

    # Validate rating
    raw = b.get("rating")

    if isinstance(raw, bool) or not isinstance(raw, (int, str)) or not str(raw).strip().isdigit():
        return bad("Rating must be a whole number from 1 to 5")

    rating = int(raw)

    if not 1 <= rating <= 5:
        return bad("Rating must be a whole number from 1 to 5")

    # Validate comment
    comment = b.get("comment", "")

    if comment is None:
        comment = ""

    if not isinstance(comment, str):
        return bad("Comment must be text")

    comment = comment.strip()

    if len(comment) > 1000:
        return bad("Comment must not exceed 1000 characters")

    # Comments are required for ratings from 1 to 3
    if rating <= 3 and not comment:
        return bad("Please explain what you did not like about the ride")

    # Check ride ownership and status
    ride, err = load_owned_ride(ride_id)

    if err:
        return err

    if ride["status"] != "completed":
        return bad("Only a completed ride can be rated", 409)

    if ride["ride_rating"] is not None:
        return bad("This ride is already rated", 409)

    db = get_db()

    try:
        db.execute("BEGIN")

        cur = db.execute("""
            UPDATE rides
            SET ride_rating = ?, ride_comment = ?
            WHERE ride_id = ? AND ride_rating IS NULL
        """, (rating, comment or None, ride_id))

        if cur.rowcount != 1:
            db.rollback()
            return bad("This ride is already rated", 409)

        # Recalculate driver's average rating
        recalc_driver_rating(ride["driver_id"], commit=False)

        db.commit()

    except sqlite3.Error:
        db.rollback()
        return bad("Transaction error, changes rolled back", 500)

    new = db.execute(
        "SELECT rating FROM drivers WHERE driver_id=?",
        (ride["driver_id"],)
    ).fetchone()[0]

    return jsonify({
        "ride_id": ride_id,
        "ride_rating": rating,
        "ride_comment": comment or None,
        "driver_rating": new
    })

# ---------------------------------------------------------------------------
# DRIVER
# ---------------------------------------------------------------------------
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
    month = datetime.now().strftime("%Y-%m")
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
    month = datetime.now().strftime("%Y-%m")
    return jsonify({
        "passengers": one("SELECT COUNT(*) FROM passengers"),
        "drivers": one("SELECT COUNT(*) FROM drivers"),
        "cars": one("SELECT COUNT(*) FROM cars"),
        "rides": one("SELECT COUNT(*) FROM rides"),
        "payments": one("SELECT COUNT(*) FROM payments"),
        "active_rides": one("SELECT COUNT(*) FROM rides WHERE status='requested'"),
        "free_drivers": one("""SELECT COUNT(*) FROM drivers d WHERE EXISTS (SELECT 1 FROM cars c WHERE c.driver_id=d.driver_id)
                               AND NOT EXISTS (SELECT 1 FROM rides r WHERE r.driver_id=d.driver_id AND r.status='requested')"""),
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
    month = request.args.get("month") or (months[0] if months else datetime.now().strftime("%Y-%m"))
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


@app.post("/api/reset")
@require("admin")
def api_reset():
    close_db(None)
    init_db(force=True)
    return jsonify({"ok": True})


init_db()

if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
