-- Migration 003: Add passenger comments to ride ratings

ALTER TABLE rides
ADD COLUMN ride_comment TEXT
CHECK (ride_comment IS NULL OR length(ride_comment) <= 1000);