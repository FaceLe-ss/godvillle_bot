from __future__ import annotations

from pathlib import Path

import httpx

from godville_bot.godville_client import GodvilleClient
from godville_bot.notifier import BossMonitorService
from godville_bot.storage import BotStorage


async def test_dungeon_multi_round_dedup_and_second_boss_notification(tmp_path: Path) -> None:
    storage = BotStorage(tmp_path / "bot.db")
    storage.set_credentials(42, "ТестБог", "tok123")
    storage.add_name_filters(42, ["Днищеброд"])
    storage.set_level_filters(42, [3])

    timeline = [
        # T=0: First encounter with Днищеброд -> SHOULD notify
        {
            "name": "Авантюрист",
            "level": 90,
            "health": 80,
            "max_health": 100,
            "arena_fight": True,
            "fight_type": "dungeon",
            "diary_last": "Навстречу выскочил Днищеброд!",
        },
        # T=1: Mid-fight generic round -> MUST NOT reset dedup or notify
        {
            "name": "Авантюрист",
            "level": 90,
            "health": 60,
            "max_health": 100,
            "arena_fight": True,
            "fight_type": "dungeon",
            "diary_last": "Герой пропустил тяжёлый удар, но устоял на ногах.",
        },
        # T=2: Same boss mentioned again in next round -> MUST NOT duplicate
        {
            "name": "Авантюрист",
            "level": 90,
            "health": 50,
            "max_health": 100,
            "arena_fight": True,
            "fight_type": "dungeon",
            "diary_last": "Днищеброд яростно рычит и готовит атаку!",
        },
        # T=3: Victory -> MUST reset dedup without sending encounter alert
        {
            "name": "Авантюрист",
            "level": 90,
            "health": 55,
            "max_health": 100,
            "arena_fight": True,
            "fight_type": "dungeon",
            "diary_last": "Днищеброд повержен! Отряд забирает запчасти.",
        },
        # T=4: Corridor step -> no alert
        {
            "name": "Авантюрист",
            "level": 90,
            "health": 70,
            "max_health": 100,
            "arena_fight": True,
            "fight_type": "dungeon",
            "diary_last": "Герои осторожно шагают по тёмному коридору на север.",
        },
        # T=5: Second matching boss in same dungeon -> SHOULD notify again
        {
            "name": "Авантюрист",
            "level": 90,
            "health": 70,
            "max_health": 100,
            "arena_fight": True,
            "fight_type": "dungeon",
            "diary_last": "С боем прорываемся мимо Великотушного!",
        },
    ]
    idx = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal idx
        payload = timeline[idx]
        idx += 1
        return httpx.Response(200, json=payload)

    sent: list[tuple[int, str]] = []

    async def send_msg(chat_id: int, text: str) -> None:
        sent.append((chat_id, text))

    client = GodvilleClient(transport=httpx.MockTransport(handler))
    monitor = BossMonitorService(storage, client, send_msg, poll_interval_seconds=60)
    try:
        for step in range(len(timeline)):
            user = storage.get_user(42)
            assert user is not None
            await monitor.poll_user(user, now_monotonic=float(step * 60))

        assert len(sent) == 2
        assert "Днищеброд" in sent[0][1]
        assert "Великотушного" in sent[1][1] or "Великотушный" in sent[1][1]
        assert "Уровень / абилки:</b> 3" in sent[0][1]
    finally:
        await client.close()
        storage.close()


async def test_token_warning_sent_once_and_recovers(tmp_path: Path) -> None:
    storage = BotStorage(tmp_path / "bot.db")
    storage.set_credentials(77, "Бог", "bad_token")

    responses = [
        {"name": "Герой", "godname": "Бог", "level": 40, "max_health": 100},
        {"name": "Герой", "godname": "Бог", "level": 40, "max_health": 100},
        {
            "name": "Герой",
            "godname": "Бог",
            "level": 40,
            "health": 90,
            "max_health": 100,
            "arena_fight": True,
            "fight_type": "sail",
            "diary_last": "Ковчег встретил Левиафан 3 уровня <Опасный>!",
        },
    ]
    idx = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal idx
        payload = responses[idx]
        idx += 1
        return httpx.Response(200, json=payload)

    sent: list[tuple[int, str]] = []

    async def send_msg(chat_id: int, text: str) -> None:
        sent.append((chat_id, text))

    client = GodvilleClient(transport=httpx.MockTransport(handler))
    monitor = BossMonitorService(storage, client, send_msg, poll_interval_seconds=60)
    try:
        for step in range(len(responses)):
            user = storage.get_user(77)
            assert user is not None
            await monitor.poll_user(user, now_monotonic=float(step * 60))

        assert len(sent) == 2
        assert "Не удалось получить приватные данные Годвилля" in sent[0][1]
        assert "Море (заплыв)" in sent[1][1]
        # HTML-unsafe '<Опасный>' must be escaped in output
        assert "&lt;Опасный&gt;" in sent[1][1]
    finally:
        await client.close()
        storage.close()


async def test_rate_limit_triggers_backoff_and_skips_next_poll(tmp_path: Path) -> None:
    storage = BotStorage(tmp_path / "bot.db")
    storage.set_credentials(88, "Бог", "tok")
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, text="Too many requests")

    async def send_msg(_: int, __: str) -> None:
        pass

    client = GodvilleClient(transport=httpx.MockTransport(handler))
    monitor = BossMonitorService(storage, client, send_msg, poll_interval_seconds=60)
    try:
        user = storage.get_user(88)
        assert user is not None
        await monitor.poll_user(user, now_monotonic=100.0)
        await monitor.poll_user(user, now_monotonic=150.0)  # skipped due to 120s backoff
        assert calls == 1

        await monitor.poll_user(user, now_monotonic=250.0)  # after backoff expires
        assert calls == 2
    finally:
        await client.close()
        storage.close()


async def test_unknown_entry_and_subsequent_boss_in_sail(tmp_path: Path) -> None:
    storage = BotStorage(tmp_path / "bot.db")
    storage.set_credentials(99, "Мореход", "tok")
    storage.add_name_filters(99, ["Кракен"])
    storage.toggle_notify_unknown(99)  # enable unknown entry heads-up

    timeline = [
        # T=0: Sail starts without boss in diary_last -> 1 heads-up notification
        {
            "name": "Капитан",
            "arena_fight": True,
            "fight_type": "sail",
            "diary_last": "Ковчег вышел в открытое море.",
        },
        # T=1: Still sailing peacefully -> suppressed
        {
            "name": "Капитан",
            "arena_fight": True,
            "fight_type": "sail",
            "diary_last": "Ветер попутный, идём по курсу.",
        },
        # T=2: Matching boss Kraken appears -> 2nd notification
        {
            "name": "Капитан",
            "arena_fight": True,
            "fight_type": "sail",
            "diary_last": "Из пучины всплыл огромный Кракен!",
        },
    ]
    idx = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal idx
        payload = timeline[idx]
        idx += 1
        return httpx.Response(200, json=payload)

    sent: list[tuple[int, str]] = []

    async def send_msg(chat_id: int, text: str) -> None:
        sent.append((chat_id, text))

    client = GodvilleClient(transport=httpx.MockTransport(handler))
    monitor = BossMonitorService(storage, client, send_msg, poll_interval_seconds=60)
    try:
        for step in range(len(timeline)):
            user = storage.get_user(99)
            assert user is not None
            await monitor.poll_user(user, now_monotonic=float(step * 60))

        assert len(sent) == 2
        assert "открытое море" in sent[0][1]
        assert "Кракен" in sent[1][1]
    finally:
        await client.close()
        storage.close()
