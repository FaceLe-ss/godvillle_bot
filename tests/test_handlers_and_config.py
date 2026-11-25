from __future__ import annotations

from pathlib import Path

from godville_bot.config import Settings
from godville_bot.godville_client import GodvilleClient
from godville_bot.handlers import (
    _build_webapp_url_with_state,
    _format_user_summary,
    _uses_send_data_mode,
    build_settings_keyboard,
    create_router,
)
from godville_bot.storage import BotStorage


def test_settings_from_env(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "BOT_TOKEN=test_token_123\n"
        "POLL_INTERVAL_SECONDS=10\n"
        "ALLOWED_TELEGRAM_IDS=111, 222\n"
        "GODVILLE_BASE_URL=https://godville.net/\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.delenv("POLL_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("ALLOWED_TELEGRAM_IDS", raising=False)
    monkeypatch.delenv("GODVILLE_BASE_URL", raising=False)

    settings = Settings.from_env(env_file)
    assert settings.bot_token == "test_token_123"
    # Enforces minimum safe polling floor
    assert settings.poll_interval_seconds == 25
    assert settings.allowed_telegram_ids == frozenset({111, 222})
    assert settings.godville_base_url == "https://godville.net"


async def test_handlers_keyboard_and_summary_mask_token(tmp_path: Path) -> None:
    storage = BotStorage(tmp_path / "bot.db")
    client = GodvilleClient()
    try:
        storage.set_credentials(55, "ТестБог", "super_secret_token_999")
        storage.add_name_filters(55, ["Днищеброд"])
        storage.toggle_level_filter(55, 3)
        user = storage.get_user(55)
        assert user is not None

        summary = _format_user_summary(user)
        assert "ТестБог" in summary
        assert "super_secret_token_999" not in summary
        assert "sup***999" in summary
        assert "Днищеброд" in summary
        assert "3 ур." in summary

        kb = build_settings_keyboard(user, webapp_url="https://example.github.io/godville-boss-bot/")
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "lvl:3" in callbacks
        assert "ft:dungeon" in callbacks
        assert "ft:sail" in callbacks
        assert "ft:boss" in callbacks
        assert "ft:boss_m" in callbacks
        assert "mode:smart" in callbacks
        assert "action:open_webapp" in callbacks

        assert _uses_send_data_mode("https://user.github.io/repo/") is True
        assert _uses_send_data_mode("https://user.github.io/repo/?api=https://bot.workers.dev") is False
        encoded_url = _build_webapp_url_with_state("https://user.github.io/repo/", user)
        assert "state=" in encoded_url
        assert "super_secret_token_999" not in encoded_url

        router = create_router(storage=storage, client=client, webapp_url="https://bot.workers.dev/")
        assert router is not None
    finally:
        await client.close()
        storage.close()
