from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


DEFAULT_FIGHT_TYPES: tuple[str, ...] = ("dungeon", "sail")
VALID_FILTER_MODES: tuple[str, ...] = ("smart", "strict", "all")


@dataclass(frozen=True, slots=True)
class UserConfig:
    """Stored Telegram user subscription and Godville filter configuration."""

    telegram_id: int
    god_name: str | None
    api_token: str | None
    base_url: str
    enabled: bool
    fight_types: tuple[str, ...]
    name_filters: tuple[str, ...]
    level_filters: tuple[int, ...]
    filter_mode: str
    notify_unknown_entry: bool
    last_fight_type: str | None
    last_diary: str | None
    last_notified_key: str | None
    last_notified_at: str | None
    token_warning_sent: bool


class BotStorage:
    """SQLite persistence layer for user credentials, filters, and dedup state."""

    def __init__(self, db_path: Path | str, default_base_url: str = "https://godville.net") -> None:
        self.db_path = Path(db_path)
        self.default_base_url = default_base_url.rstrip("/")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    god_name TEXT,
                    api_token TEXT,
                    base_url TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    fight_types TEXT NOT NULL DEFAULT '["dungeon", "sail"]',
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
                )
                """
            )

    def close(self) -> None:
        self._conn.close()

    def _row_to_user(self, row: sqlite3.Row) -> UserConfig:
        return UserConfig(
            telegram_id=int(row["telegram_id"]),
            god_name=row["god_name"],
            api_token=row["api_token"],
            base_url=row["base_url"],
            enabled=bool(row["enabled"]),
            fight_types=tuple(json.loads(row["fight_types"])),
            name_filters=tuple(json.loads(row["name_filters"])),
            level_filters=tuple(int(x) for x in json.loads(row["level_filters"])),
            filter_mode=row["filter_mode"],
            notify_unknown_entry=bool(row["notify_unknown_entry"]),
            last_fight_type=row["last_fight_type"],
            last_diary=row["last_diary"],
            last_notified_key=row["last_notified_key"],
            last_notified_at=row["last_notified_at"],
            token_warning_sent=bool(row["token_warning_sent"]),
        )

    def get_or_create_user(self, telegram_id: int) -> UserConfig:
        row = self._conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        if row is not None:
            return self._row_to_user(row)

        now = _utc_now_iso()
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO users (
                    telegram_id, base_url, enabled, fight_types,
                    name_filters, level_filters, filter_mode,
                    notify_unknown_entry, token_warning_sent, created_at, updated_at
                ) VALUES (?, ?, 1, ?, '[]', '[]', 'smart', 0, 0, ?, ?)
                """,
                (
                    telegram_id,
                    self.default_base_url,
                    json.dumps(list(DEFAULT_FIGHT_TYPES)),
                    now,
                    now,
                ),
            )
        row = self._conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        assert row is not None
        return self._row_to_user(row)

    def get_user(self, telegram_id: int) -> UserConfig | None:
        row = self._conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        return self._row_to_user(row) if row is not None else None

    def list_active_users(self) -> list[UserConfig]:
        rows = self._conn.execute(
            """
            SELECT * FROM users
            WHERE enabled = 1
              AND god_name IS NOT NULL AND TRIM(god_name) != ''
              AND api_token IS NOT NULL AND TRIM(api_token) != ''
            """
        ).fetchall()
        return [self._row_to_user(r) for r in rows]

    def set_credentials(
        self,
        telegram_id: int,
        god_name: str,
        api_token: str,
        base_url: str | None = None,
    ) -> UserConfig:
        user = self.get_or_create_user(telegram_id)
        now = _utc_now_iso()
        resolved_base = (base_url or user.base_url or self.default_base_url).rstrip("/")
        with self._conn:
            self._conn.execute(
                """
                UPDATE users
                SET god_name = ?,
                    api_token = ?,
                    base_url = ?,
                    token_warning_sent = 0,
                    last_notified_key = NULL,
                    updated_at = ?
                WHERE telegram_id = ?
                """,
                (god_name.strip(), api_token.strip(), resolved_base, now, telegram_id),
            )
        return self.get_or_create_user(telegram_id)

    def set_enabled(self, telegram_id: int, enabled: bool) -> UserConfig:
        self.get_or_create_user(telegram_id)
        with self._conn:
            self._conn.execute(
                "UPDATE users SET enabled = ?, updated_at = ? WHERE telegram_id = ?",
                (1 if enabled else 0, _utc_now_iso(), telegram_id),
            )
        return self.get_or_create_user(telegram_id)

    def add_name_filters(self, telegram_id: int, names: Iterable[str]) -> UserConfig:
        user = self.get_or_create_user(telegram_id)
        existing = list(user.name_filters)
        lowered = {x.casefold() for x in existing}
        for name in names:
            cleaned = " ".join(name.split())
            if cleaned and cleaned.casefold() not in lowered:
                existing.append(cleaned)
                lowered.add(cleaned.casefold())
        with self._conn:
            self._conn.execute(
                "UPDATE users SET name_filters = ?, updated_at = ? WHERE telegram_id = ?",
                (json.dumps(existing, ensure_ascii=False), _utc_now_iso(), telegram_id),
            )
        return self.get_or_create_user(telegram_id)

    def remove_name_filter(self, telegram_id: int, name: str) -> tuple[UserConfig, bool]:
        user = self.get_or_create_user(telegram_id)
        target = " ".join(name.split()).casefold()
        updated = [item for item in user.name_filters if item.casefold() != target]
        removed = len(updated) != len(user.name_filters)
        if removed:
            with self._conn:
                self._conn.execute(
                    "UPDATE users SET name_filters = ?, updated_at = ? WHERE telegram_id = ?",
                    (json.dumps(updated, ensure_ascii=False), _utc_now_iso(), telegram_id),
                )
        return self.get_or_create_user(telegram_id), removed

    def clear_name_filters(self, telegram_id: int) -> UserConfig:
        self.get_or_create_user(telegram_id)
        with self._conn:
            self._conn.execute(
                "UPDATE users SET name_filters = '[]', updated_at = ? WHERE telegram_id = ?",
                (_utc_now_iso(), telegram_id),
            )
        return self.get_or_create_user(telegram_id)

    def toggle_level_filter(self, telegram_id: int, level: int) -> UserConfig:
        if level not in (1, 2, 3, 4):
            raise ValueError("Boss level must be between 1 and 4")
        user = self.get_or_create_user(telegram_id)
        levels = set(user.level_filters)
        if level in levels:
            levels.remove(level)
        else:
            levels.add(level)
        return self.set_level_filters(telegram_id, sorted(levels))

    def set_level_filters(self, telegram_id: int, levels: Iterable[int]) -> UserConfig:
        self.get_or_create_user(telegram_id)
        normalized = sorted({int(lvl) for lvl in levels if int(lvl) in (1, 2, 3, 4)})
        with self._conn:
            self._conn.execute(
                "UPDATE users SET level_filters = ?, updated_at = ? WHERE telegram_id = ?",
                (json.dumps(normalized), _utc_now_iso(), telegram_id),
            )
        return self.get_or_create_user(telegram_id)

    def toggle_fight_type(self, telegram_id: int, fight_type: str) -> UserConfig:
        user = self.get_or_create_user(telegram_id)
        current = list(user.fight_types)
        if fight_type in current:
            current = [ft for ft in current if ft != fight_type]
        else:
            current.append(fight_type)
        with self._conn:
            self._conn.execute(
                "UPDATE users SET fight_types = ?, updated_at = ? WHERE telegram_id = ?",
                (json.dumps(current), _utc_now_iso(), telegram_id),
            )
        return self.get_or_create_user(telegram_id)

    def set_filter_mode(self, telegram_id: int, mode: str) -> UserConfig:
        if mode not in VALID_FILTER_MODES:
            raise ValueError(f"Unsupported filter mode: {mode}")
        self.get_or_create_user(telegram_id)
        with self._conn:
            self._conn.execute(
                "UPDATE users SET filter_mode = ?, updated_at = ? WHERE telegram_id = ?",
                (mode, _utc_now_iso(), telegram_id),
            )
        return self.get_or_create_user(telegram_id)

    def toggle_notify_unknown(self, telegram_id: int) -> UserConfig:
        user = self.get_or_create_user(telegram_id)
        next_val = 0 if user.notify_unknown_entry else 1
        with self._conn:
            self._conn.execute(
                "UPDATE users SET notify_unknown_entry = ?, updated_at = ? WHERE telegram_id = ?",
                (next_val, _utc_now_iso(), telegram_id),
            )
        return self.get_or_create_user(telegram_id)

    def apply_webapp_settings(self, telegram_id: int, payload: dict[str, object]) -> UserConfig:
        """Apply validated filter and status settings submitted from the Telegram Mini App."""
        user = self.get_or_create_user(telegram_id)

        allowed_fight_types = {"dungeon", "sail", "boss", "boss_m"}
        raw_ft = payload.get("fight_types")
        if isinstance(raw_ft, list):
            fight_types = [str(ft) for ft in raw_ft if str(ft) in allowed_fight_types]
        else:
            fight_types = list(user.fight_types)

        raw_names = payload.get("name_filters")
        if isinstance(raw_names, list):
            deduped_names: list[str] = []
            seen: set[str] = set()
            for item in raw_names:
                cleaned = " ".join(str(item).split())
                if cleaned and cleaned.casefold() not in seen:
                    deduped_names.append(cleaned)
                    seen.add(cleaned.casefold())
            name_filters = deduped_names
        else:
            name_filters = list(user.name_filters)

        raw_levels = payload.get("level_filters")
        if isinstance(raw_levels, list):
            level_filters = sorted(
                {int(lvl) for lvl in raw_levels if str(lvl).isdigit() and int(lvl) in (1, 2, 3, 4)}
            )
        else:
            level_filters = list(user.level_filters)

        raw_mode = str(payload.get("filter_mode", user.filter_mode))
        filter_mode = raw_mode if raw_mode in VALID_FILTER_MODES else user.filter_mode

        enabled = bool(payload.get("enabled", user.enabled))
        notify_unknown = bool(payload.get("notify_unknown_entry", user.notify_unknown_entry))

        god_name = user.god_name
        raw_god = payload.get("god_name")
        if isinstance(raw_god, str) and raw_god.strip():
            god_name = raw_god.strip()

        api_token = user.api_token
        raw_token = payload.get("api_token")
        if isinstance(raw_token, str) and raw_token.strip():
            api_token = raw_token.strip()

        with self._conn:
            self._conn.execute(
                """
                UPDATE users
                SET god_name = ?,
                    api_token = ?,
                    enabled = ?,
                    fight_types = ?,
                    name_filters = ?,
                    level_filters = ?,
                    filter_mode = ?,
                    notify_unknown_entry = ?,
                    updated_at = ?
                WHERE telegram_id = ?
                """,
                (
                    god_name,
                    api_token,
                    1 if enabled else 0,
                    json.dumps(fight_types),
                    json.dumps(name_filters, ensure_ascii=False),
                    json.dumps(level_filters),
                    filter_mode,
                    1 if notify_unknown else 0,
                    _utc_now_iso(),
                    telegram_id,
                ),
            )
        return self.get_or_create_user(telegram_id)

    def update_poll_state(
        self,
        telegram_id: int,
        *,
        last_fight_type: str | None,
        last_diary: str | None,
        last_notified_key: str | None,
        notified_now: bool = False,
        token_warning_sent: bool | None = None,
    ) -> None:
        now = _utc_now_iso()
        fields = [
            "last_fight_type = ?",
            "last_diary = ?",
            "last_notified_key = ?",
            "updated_at = ?",
        ]
        params: list[object] = [last_fight_type, last_diary, last_notified_key, now]
        if notified_now:
            fields.append("last_notified_at = ?")
            params.append(now)
        if token_warning_sent is not None:
            fields.append("token_warning_sent = ?")
            params.append(1 if token_warning_sent else 0)
        params.append(telegram_id)
        sql = f"UPDATE users SET {', '.join(fields)} WHERE telegram_id = ?"
        with self._conn:
            self._conn.execute(sql, params)
