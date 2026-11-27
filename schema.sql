-- Mini Taxi Service · Almaty
-- 5 tables from Task 9: PASSENGERS, DRIVERS, CARS, RIDES, PAYMENTS
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS passengers (
    passenger_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name         TEXT    NOT NULL,
    phone             TEXT    NOT NULL UNIQUE,
    email             TEXT    UNIQUE,
    registration_date TEXT    NOT NULL DEFAULT (date('now')),
    password_hash     TEXT
);

CREATE TABLE IF NOT EXISTS drivers (
    driver_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name      TEXT    NOT NULL,
    phone          TEXT    NOT NULL UNIQUE,
    email          TEXT    UNIQUE,
    license_number TEXT    NOT NULL UNIQUE,
    rating         REAL    NOT NULL DEFAULT 5.0 CHECK (rating BETWEEN 1 AND 5),
    password_hash  TEXT
);

CREATE TABLE IF NOT EXISTS cars (
    car_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    driver_id    INTEGER NOT NULL REFERENCES drivers(driver_id),
    plate_number TEXT    NOT NULL UNIQUE,
    model        TEXT    NOT NULL,
    color        TEXT
);

CREATE TABLE IF NOT EXISTS rides (
    ride_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    passenger_id    INTEGER NOT NULL REFERENCES passengers(passenger_id),
    driver_id       INTEGER NOT NULL REFERENCES drivers(driver_id),
    car_id          INTEGER NOT NULL REFERENCES cars(car_id),
    pickup_address  TEXT    NOT NULL,
    dropoff_address TEXT    NOT NULL,
    start_time      TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'requested'
                    CHECK (status IN ('requested','completed','cancelled')),
    price           INTEGER NOT NULL CHECK (price > 0),
    ride_rating     INTEGER CHECK (ride_rating BETWEEN 1 AND 5),
    ride_comment    TEXT CHECK (ride_comment IS NULL OR length(ride_comment) <= 1000),
    feedback_tags   TEXT
);

CREATE TABLE IF NOT EXISTS payments (
    payment_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    ride_id        INTEGER NOT NULL REFERENCES rides(ride_id),
    amount         INTEGER NOT NULL CHECK (amount > 0),  -- KZT
    method         TEXT    NOT NULL CHECK (method IN ('cash','card')),
    payment_status TEXT    NOT NULL CHECK (payment_status IN ('paid','failed')),
    paid_at        TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rides_passenger ON rides(passenger_id);
CREATE INDEX IF NOT EXISTS idx_rides_driver    ON rides(driver_id);
CREATE INDEX IF NOT EXISTS idx_payments_ride   ON payments(ride_id);

-- Driver shifts: a driver is "online" while they have a shift with no ended_at
CREATE TABLE IF NOT EXISTS driver_shifts (
    shift_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    driver_id  INTEGER NOT NULL REFERENCES drivers(driver_id),
    started_at TEXT    NOT NULL,
    ended_at   TEXT,                                  -- empty while the driver is online
    CHECK (ended_at IS NULL OR ended_at >= started_at)
);

CREATE INDEX IF NOT EXISTS idx_shifts_driver ON driver_shifts(driver_id);
-- a driver can have only ONE open shift at a time
CREATE UNIQUE INDEX IF NOT EXISTS one_open_shift_per_driver ON driver_shifts(driver_id) WHERE ended_at IS NULL;

-- Fare rules: every price the passenger pays, editable by the admin
CREATE TABLE IF NOT EXISTS fare_rules (
    rule_key   TEXT    PRIMARY KEY,                    -- base, per_km, minimum, mountain, airport, night, rush
    name       TEXT    NOT NULL,
    kind       TEXT    NOT NULL CHECK (kind IN ('fixed', 'per_km', 'minimum', 'surcharge', 'multiplier')),
    amount     REAL    NOT NULL CHECK (amount > 0),    -- KZT, or a factor for multipliers
    applies_to TEXT    NOT NULL,                       -- when the rule is used, in words
    active     INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    updated_at TEXT,
    CHECK (kind <> 'multiplier' OR amount BETWEEN 1 AND 3)
);

-- Live conditions that change the price (migration 007).
-- keys: traffic (free / moderate / heavy), accident_district ('' or a district name),
--       weather_mode (auto = from the internet, or clear / rain / snow set by the admin)
CREATE TABLE IF NOT EXISTS conditions (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT
);

-- Saved places: a passenger's favourite addresses, e.g. "Home" or "University" (migration 008)
CREATE TABLE IF NOT EXISTS saved_places (
    place_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    passenger_id INTEGER NOT NULL REFERENCES passengers(passenger_id) ON DELETE CASCADE,
    label        TEXT    NOT NULL CHECK (length(trim(label)) BETWEEN 1 AND 30),
    address      TEXT    NOT NULL,                     -- one of the Almaty places on the map
    icon         TEXT    NOT NULL DEFAULT 'pin' CHECK (icon IN ('home', 'work', 'study', 'heart', 'pin')),
    created_at   TEXT    NOT NULL,
    UNIQUE (passenger_id, label COLLATE NOCASE)        -- no two "Home" places for one passenger
);
