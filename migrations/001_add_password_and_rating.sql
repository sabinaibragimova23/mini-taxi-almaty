-- Migration 001: password_hash for login, ride_rating for driver ratings
-- Run once on an existing taxi.db (DB Browser for SQLite -> Execute SQL).
-- A new database gets these columns automatically from schema.sql.

ALTER TABLE passengers ADD COLUMN password_hash TEXT;
ALTER TABLE drivers    ADD COLUMN password_hash TEXT;
ALTER TABLE rides      ADD COLUMN ride_rating INTEGER CHECK (ride_rating BETWEEN 1 AND 5);
