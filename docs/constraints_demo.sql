-- Run each statement one by one in DB Browser for SQLite (tab "Execute SQL")
-- on taxi.db. Every one must FAIL: that is the proof the database protects its data.
-- (DB Browser turns foreign keys on by default; the line below makes sure.)
PRAGMA foreign_keys = ON;

-- 1. Foreign key: a car for a driver that does not exist
INSERT INTO cars (driver_id, plate_number, model) VALUES (99, '111 AAA 02', 'Kia Rio');
-- expected: FOREIGN KEY constraint failed

-- 2. UNIQUE: the same phone twice
INSERT INTO drivers (full_name, phone, license_number) VALUES ('Test', '+7 701 555 20 11', 'ZZ 0000001');
-- expected: UNIQUE constraint failed: drivers.phone

-- 3. CHECK: rating outside 1..5
INSERT INTO drivers (full_name, phone, license_number, rating) VALUES ('Test', '+7 700 111 11 11', 'ZZ 0000002', 7);
-- expected: CHECK constraint failed: rating BETWEEN 1 AND 5

-- 4. CHECK: unknown ride status
UPDATE rides SET status = 'flying' WHERE ride_id = 1;
-- expected: CHECK constraint failed

-- 5. CHECK: unknown payment method
INSERT INTO payments (ride_id, amount, method, payment_status, paid_at) VALUES (1, 1000, 'bitcoin', 'paid', '2026-11-02 10:00');
-- expected: CHECK constraint failed

-- 6. NOT NULL: passenger without a name
INSERT INTO passengers (phone) VALUES ('+7 700 222 22 22');
-- expected: NOT NULL constraint failed: passengers.full_name

-- Useful SELECT to show how the tables connect (one ride with everything joined):
SELECT r.ride_id, p.full_name AS passenger, d.full_name AS driver, c.plate_number,
       r.pickup_address, r.dropoff_address, r.status, r.price,
       pay.method, pay.payment_status
FROM rides r
JOIN passengers p ON p.passenger_id = r.passenger_id
JOIN drivers d    ON d.driver_id    = r.driver_id
JOIN cars c       ON c.car_id       = r.car_id
LEFT JOIN payments pay ON pay.ride_id = r.ride_id
WHERE r.ride_id = 1;

-- 7. CHECK on the new column: ride rating must be 1..5
UPDATE rides SET ride_rating = 6 WHERE ride_id = 1;
-- expected: CHECK constraint failed

-- 8. A correct rating is accepted
UPDATE rides SET ride_rating = 5 WHERE ride_id = 1;
-- expected: no error, 1 row changed

-- 9. UNIQUE (partial index): a driver cannot have two open shifts at once
--    (driver 1 is online in the demo data)
INSERT INTO driver_shifts (driver_id, started_at) VALUES (1, '2026-11-14 12:00');
-- expected: UNIQUE constraint failed: driver_shifts.driver_id

-- 10. CHECK: a shift cannot end before it starts
INSERT INTO driver_shifts (driver_id, started_at, ended_at) VALUES (6, '2026-11-14 12:00', '2026-11-14 09:00');
-- expected: CHECK constraint failed

-- 11. FOREIGN KEY: a shift for a driver that does not exist
INSERT INTO driver_shifts (driver_id, started_at) VALUES (99, '2026-11-14 12:00');
-- expected: FOREIGN KEY constraint failed
