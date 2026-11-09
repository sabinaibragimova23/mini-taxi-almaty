-- Migration 002: drivers get an email so they can log in with email + password.
-- The app applies this (and migration 001) automatically on start; this file is for the docs / DB Browser.
-- Passwords are never stored in plain text: password_hash holds a werkzeug hash (generate_password_hash).

ALTER TABLE drivers ADD COLUMN email TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_drivers_email ON drivers(email);
