from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx
import pytest
from aiohttp.test_utils import TestClient, TestServer

from godville_bot.godville_client import GodvilleClient
from godville_bot.storage import BotStorage
from godville_bot.web_server import (
    InitDataError,
    create_web_app,
    verify_telegram_init_data,
)


def _make_init_data(bot_token: str, user_id: int, *, auth_date: int | None = None) -> str:
    ts = int(time.time()) if auth_date is None else auth_date
    fields = {
        "auth_date": str(ts),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps({"id": user_id, "first_name": "Test"}, separators=(",", ":")),
    }
    data_check_string = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    signature = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    fields["hash"] = signature
    return urlencode(fields)


def test_verify_telegram_init_data_valid_and_errors() -> None:
    bot_token = "123456:TEST_TOKEN"
    valid = _make_init_data(bot_token, 4242, auth_date=1_700_000_000)
    assert verify_telegram_init_data(valid, bot_token, now_timestamp=1_700_000_100) == 4242

    with pytest.raises(InitDataError, match="Expired"):
        verify_telegram_init_data(valid, bot_token, now_timestamp=1_700_200_000)

    tampered = valid.replace("4242", "9999")
    with pytest.raises(InitDataError, match="Invalid initData signature"):
        verify_telegram_init_data(tampered, bot_token, now_timestamp=1_700_000_100)


async def test_web_app_serves_miniapp_and_api_endpoints(tmp_path: Path) -> None:
    bot_token = "123456:TEST_TOKEN"
    storage = BotStorage(tmp_path / "bot.db")

    def gv_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "name": "Сэр Тест",
                "godname": "Тестобог",
                "level": 77,
                "health": 88,
                "max_health": 100,
                "arena_fight": True,
                "fight_type": "dungeon",
                "diary_last": "Встретили Днищеброда!",
            },
        )

    gv_client = GodvilleClient(transport=httpx.MockTransport(gv_handler))
    webapp_dir = Path(__file__).resolve().parents[1] / "webapp"
    app = create_web_app(
        bot_token=bot_token,
        storage=storage,
        client=gv_client,
        webapp_dir=webapp_dir,
    )

    init_data = _make_init_data(bot_token, 777)
    headers = {"X-Telegram-Init-Data": init_data}

    async with TestClient(TestServer(app)) as tc:
        health = await tc.get("/health")
        assert health.status == 200
        assert await health.json() == {"ok": True}

        index_resp = await tc.get("/")
        assert index_resp.status == 200
        assert "Godville Boss Filter" in await index_resp.text()

        preflight = await tc.options("/api/state")
        assert preflight.status == 204
        assert preflight.headers.get("Access-Control-Allow-Origin") == "*"

        unauth = await tc.get("/api/state")
        assert unauth.status == 401

        get_resp = await tc.get("/api/state", headers=headers)
        assert get_resp.status == 200
        data = await get_resp.json()
        assert data["fight_types"] == ["dungeon", "sail"]
        assert data["has_token"] is False

        post_resp = await tc.post(
            "/api/state",
            headers=headers,
            json={
                "enabled": True,
                "fight_types": ["dungeon", "sail", "boss"],
                "name_filters": ["Днищеброд", "  Великотушный "],
                "level_filters": [2, 3],
                "filter_mode": "strict",
                "notify_unknown_entry": True,
            },
        )
        assert post_resp.status == 200
        updated = await post_resp.json()
        assert updated["fight_types"] == ["dungeon", "sail", "boss"]
        assert updated["name_filters"] == ["Днищеброд", "Великотушный"]
        assert updated["level_filters"] == [2, 3]
        assert updated["filter_mode"] == "strict"
        assert updated["notify_unknown_entry"] is True

        verify_resp = await tc.post(
            "/api/verify",
            headers=headers,
            json={"god_name": "Тестобог", "api_token": "secret_gv_token"},
        )
        assert verify_resp.status == 200
        verified = await verify_resp.json()
        assert verified["god_name"] == "Тестобог"
        assert verified["has_token"] is True
        assert "api_token" not in verified
        assert verified["has_private_fields"] is True
        assert verified["hero"]["name"] == "Сэр Тест"

    await gv_client.close()
    storage.close()
