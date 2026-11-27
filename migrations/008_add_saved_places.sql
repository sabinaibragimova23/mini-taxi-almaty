-- Migration 008: saved places (a passenger's favourite addresses)
-- The app creates this table on start (schema.sql). This file is for the docs and for DB Browser.

CREATE TABLE IF NOT EXISTS saved_places (
    place_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    passenger_id INTEGER NOT NULL REFERENCES passengers(passenger_id) ON DELETE CASCADE,
    label        TEXT    NOT NULL CHECK (length(trim(label)) BETWEEN 1 AND 30),
    address      TEXT    NOT NULL,
    icon         TEXT    NOT NULL DEFAULT 'pin' CHECK (icon IN ('home', 'work', 'study', 'heart', 'pin')),
    created_at   TEXT    NOT NULL,
    UNIQUE (passenger_id, label COLLATE NOCASE)
);
