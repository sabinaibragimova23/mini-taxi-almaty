-- Migration 006: Store selected ready-made feedback options for ride ratings.
ALTER TABLE rides ADD COLUMN feedback_tags TEXT;
