-- Migration 004: Store ready-made passenger feedback options for each ride
ALTER TABLE rides ADD COLUMN feedback_tags TEXT;
