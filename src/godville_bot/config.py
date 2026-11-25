from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _parse_int_set(raw: str | None) -> frozenset[int]:
    if not raw:
        return frozenset()
    result: set[int] = set()
    for part in raw.split(","):
        cleaned = part.strip()
        if not cleaned:
            continue
        result.add(int(cleaned))
    return frozenset(result)


@dataclass(frozen=True, slots=True)
class Settings:
    """Application configuration loaded from environment variables."""

    bot_token: str
    db_path: Path = Path("data/bot.db")
    godville_base_url: str = "https://godville.net"
    poll_interval_seconds: int = 60
    request_timeout_seconds: float = 15.0
    allowed_telegram_ids: frozenset[int] = frozenset()
    default_god_name: str | None = None
    default_godville_token: str | None = None
    webapp_url: str | None = None
    web_host: str = "0.0.0.0"
    web_port: int = 8080

    @classmethod
    def from_env(cls, env_file: str | Path | None = ".env") -> "Settings":
        if env_file is not None and Path(env_file).exists():
            load_dotenv(dotenv_path=env_file, override=False)

        bot_token = os.getenv("BOT_TOKEN", "").strip()
        if not bot_token:
            raise ValueError("BOT_TOKEN environment variable is required")

        db_path = Path(os.getenv("DB_PATH", "data/bot.db").strip() or "data/bot.db")
        base_url = os.getenv("GODVILLE_BASE_URL", "https://godville.net").strip().rstrip("/")
        if not base_url:
            base_url = "https://godville.net"

        raw_interval = int(os.getenv("POLL_INTERVAL_SECONDS", "60").strip() or "60")
        # Godville updates API data roughly once per minute and rate-limits aggressive polling.
        poll_interval = max(25, raw_interval)

        raw_timeout = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "15").strip() or "15")
        request_timeout = max(3.0, raw_timeout)

        allowed_ids = _parse_int_set(os.getenv("ALLOWED_TELEGRAM_IDS"))
        default_god = os.getenv("DEFAULT_GOD_NAME", "").strip() or None
        default_token = os.getenv("DEFAULT_GODVILLE_TOKEN", "").strip() or None
        webapp_url = os.getenv("WEBAPP_URL", "").strip() or None
        web_host = os.getenv("WEB_HOST", "0.0.0.0").strip() or "0.0.0.0"
        raw_port = (os.getenv("PORT") or os.getenv("WEBAPP_PORT") or "8080").strip()
        web_port = max(0, int(raw_port))

        return cls(
            bot_token=bot_token,
            db_path=db_path,
            godville_base_url=base_url,
            poll_interval_seconds=poll_interval,
            request_timeout_seconds=request_timeout,
            allowed_telegram_ids=allowed_ids,
            default_god_name=default_god,
            default_godville_token=default_token,
            webapp_url=webapp_url,
            web_host=web_host,
            web_port=web_port,
        )
