-- Migration 007: live conditions (traffic, accident, weather) change the price.
-- The app creates this table and the new prices on start; this file is for the docs and DB Browser.

CREATE TABLE IF NOT EXISTS conditions (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT
);

INSERT OR IGNORE INTO conditions (key, value) VALUES
  ('traffic', 'free'),            -- free / moderate / heavy (set by the admin)
  ('accident_district', ''),      -- '' = no accident, or a district name (set by the admin)
  ('weather_mode', 'auto');       -- auto = Open-Meteo, or clear / rain / snow (set by the admin)

INSERT OR IGNORE INTO fare_rules (rule_key, name, kind, amount, applies_to) VALUES
  ('traffic_moderate', 'Moderate traffic',    'multiplier', 1.15, 'Admin sets city traffic to Moderate'),
  ('traffic_heavy',    'Heavy traffic',       'multiplier', 1.3,  'Admin sets city traffic to Heavy'),
  ('accident',         'Accident in the area','multiplier', 1.2,  'Accident in the district of the pickup or drop-off'),
  ('rain',             'Rain',                'multiplier', 1.1,  'It is raining in Almaty (live weather)'),
  ('snow',             'Snow',                'multiplier', 1.25, 'It is snowing in Almaty (live weather)');
