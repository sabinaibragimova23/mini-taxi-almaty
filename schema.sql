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
    ride_rating     INTEGER CHECK (ride_rating BETWEEN 1 AND 5)
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
