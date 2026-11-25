CREATE TABLE IF NOT EXISTS users (
  telegram_id INTEGER PRIMARY KEY,
  god_name TEXT,
  api_token TEXT,
  base_url TEXT NOT NULL DEFAULT 'https://godville.net',
  enabled INTEGER NOT NULL DEFAULT 1,
  fight_types TEXT NOT NULL DEFAULT '["dungeon","sail"]',
  name_filters TEXT NOT NULL DEFAULT '[]',
  level_filters TEXT NOT NULL DEFAULT '[]',
  filter_mode TEXT NOT NULL DEFAULT 'smart',
  notify_unknown_entry INTEGER NOT NULL DEFAULT 0,
  last_fight_type TEXT,
  last_diary TEXT,
  last_notified_key TEXT,
  last_notified_at TEXT,
  token_warning_sent INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_active
  ON users (enabled, god_name, api_token);
