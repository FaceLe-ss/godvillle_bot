from __future__ import annotations

from pathlib import Path

from godville_bot.storage import BotStorage


def test_storage_crud_and_filters(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    storage = BotStorage(db_path)
    try:
        user = storage.get_or_create_user(1001)
        assert user.telegram_id == 1001
        assert user.fight_types == ("dungeon", "sail")
        assert user.filter_mode == "smart"
        assert user.enabled is True

        user = storage.set_credentials(1001, "МойБог", "secret123")
        assert user.god_name == "МойБог"
        assert user.api_token == "secret123"

        user = storage.add_name_filters(1001, ["Днищеброд", "  днищеброд ", "Великотушный"])
        assert user.name_filters == ("Днищеброд", "Великотушный")

        user, removed = storage.remove_name_filter(1001, "днищеброд")
        assert removed is True
        assert user.name_filters == ("Великотушный",)

        user = storage.toggle_level_filter(1001, 3)
        user = storage.toggle_level_filter(1001, 1)
        assert user.level_filters == (1, 3)
        user = storage.toggle_level_filter(1001, 1)
        assert user.level_filters == (3,)

        user = storage.toggle_fight_type(1001, "boss")
        assert "boss" in user.fight_types
        user = storage.set_filter_mode(1001, "strict")
        assert user.filter_mode == "strict"

        active = storage.list_active_users()
        assert len(active) == 1
        assert active[0].telegram_id == 1001

        storage.set_enabled(1001, False)
        assert storage.list_active_users() == []
    finally:
        storage.close()
