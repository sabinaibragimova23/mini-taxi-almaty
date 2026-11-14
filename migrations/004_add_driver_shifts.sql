-- Migration 004: driver shifts (online / offline)
-- The app creates this table automatically on start (schema.sql) and puts every
-- driver online once. This file is for the docs and for DB Browser.

CREATE TABLE IF NOT EXISTS driver_shifts (
    shift_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    driver_id  INTEGER NOT NULL REFERENCES drivers(driver_id),
    started_at TEXT    NOT NULL,
    ended_at   TEXT,
    CHECK (ended_at IS NULL OR ended_at >= started_at)
);

CREATE INDEX IF NOT EXISTS idx_shifts_driver ON driver_shifts(driver_id);
CREATE UNIQUE INDEX IF NOT EXISTS one_open_shift_per_driver ON driver_shifts(driver_id) WHERE ended_at IS NULL;

-- Put every driver online once, so booking keeps working right after the migration
INSERT INTO driver_shifts (driver_id, started_at)
SELECT driver_id, strftime('%Y-%m-%d %H:%M', 'now', 'localtime') FROM drivers;
