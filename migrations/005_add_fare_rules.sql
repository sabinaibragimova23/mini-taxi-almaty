-- Migration 005: fare rules (all prices and extra charges in the database)
-- The app creates this table on start (schema.sql) and fills it once with the
-- default prices. This file is for the docs and for DB Browser.

CREATE TABLE IF NOT EXISTS fare_rules (
    rule_key   TEXT    PRIMARY KEY,
    name       TEXT    NOT NULL,
    kind       TEXT    NOT NULL CHECK (kind IN ('fixed', 'per_km', 'minimum', 'surcharge', 'multiplier')),
    amount     REAL    NOT NULL CHECK (amount > 0),
    applies_to TEXT    NOT NULL,
    active     INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    updated_at TEXT,
    CHECK (kind <> 'multiplier' OR amount BETWEEN 1 AND 3)
);

INSERT OR IGNORE INTO fare_rules (rule_key, name, kind, amount, applies_to) VALUES
  ('base',     'Base fare',          'fixed',      500, 'Every ride'),
  ('per_km',   'Price per km',       'per_km',     140, 'Every km of the route (straight line x 1.35)'),
  ('minimum',  'Minimum fare',       'minimum',    800, 'If the ride costs less, the passenger pays this'),
  ('mountain', 'Mountain surcharge', 'surcharge',  600, 'Pickup or drop-off at Medeu or Shymbulak'),
  ('airport',  'Airport surcharge',  'surcharge',  400, 'Pickup or drop-off at Almaty Airport'),
  ('night',    'Night fare',         'multiplier', 1.2, '23:00 - 06:00'),
  ('rush',     'Rush hour',          'multiplier', 1.1, '07:00 - 10:00 and 17:00 - 20:00 on weekdays');
