from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl

from aiohttp import web

from godville_bot.boss_parser import analyze_hero_state
from godville_bot.godville_client import GodvilleApiError, GodvilleClient
from godville_bot.storage import BotStorage, UserConfig


class InitDataError(ValueError):
    """Raised when Telegram Mini App initData authentication fails."""


def verify_telegram_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age_seconds: int = 86400,
    now_timestamp: int | None = None,
) -> int:
    """Validate Telegram WebApp initData HMAC-SHA256 signature and return user ID."""
    if not init_data or not init_data.strip():
        raise InitDataError("Missing X-Telegram-Init-Data")

    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise InitDataError("Missing hash in initData")

    auth_date_raw = parsed.get("auth_date")
    if not auth_date_raw or not auth_date_raw.isdigit():
        raise InitDataError("Missing or invalid auth_date")
    now_ts = int(time.time()) if now_timestamp is None else now_timestamp
    if now_ts - int(auth_date_raw) > max_age_seconds:
        raise InitDataError("Expired initData")

    data_check_string = "\n".join(f"{k}={parsed[k]}" for k in sorted(parsed))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        raise InitDataError("Invalid initData signature")

    user_raw = parsed.get("user")
    if not user_raw:
        raise InitDataError("Missing user object in initData")
    try:
        user_obj = json.loads(user_raw)
    except ValueError as exc:
        raise InitDataError("Invalid user JSON in initData") from exc

    user_id = user_obj.get("id")
    if not isinstance(user_id, int):
        raise InitDataError("Missing numeric user.id in initData")
    return user_id


def serialize_user_for_webapp(user: UserConfig) -> dict[str, Any]:
    """Serialize UserConfig for the Mini App without leaking raw API tokens."""
    return {
        "god_name": user.god_name or "",
        "has_token": bool(user.api_token),
        "enabled": user.enabled,
        "fight_types": list(user.fight_types),
        "name_filters": list(user.name_filters),
        "level_filters": list(user.level_filters),
        "filter_mode": user.filter_mode,
        "notify_unknown_entry": user.notify_unknown_entry,
    }


def _cors_headers() -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type, X-Telegram-Init-Data",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    }


def create_web_app(
    *,
    bot_token: str,
    storage: BotStorage,
    client: GodvilleClient,
    allowed_telegram_ids: frozenset[int] = frozenset(),
    webapp_dir: Path | None = None,
) -> web.Application:
    resolved_dir = webapp_dir or (Path(__file__).resolve().parents[2] / "webapp")

    @web.middleware
    async def cors_middleware(
        request: web.Request, handler: web.Handler
    ) -> web.StreamResponse:
        if request.method == "OPTIONS":
            return web.Response(status=204, headers=_cors_headers())
        response = await handler(request)
        response.headers.update(_cors_headers())
        return response

    app = web.Application(middlewares=[cors_middleware])

    def _authenticate(request: web.Request) -> int:
        init_data = request.headers.get("X-Telegram-Init-Data", "")
        uid = verify_telegram_init_data(init_data, bot_token)
        if allowed_telegram_ids and uid not in allowed_telegram_ids:
            raise web.HTTPForbidden(
                text=json.dumps({"error": "Access denied"}),
                content_type="application/json",
            )
        return uid

    async def handle_health(_: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    async def handle_get_state(request: web.Request) -> web.Response:
        try:
            uid = _authenticate(request)
        except InitDataError as exc:
            return web.json_response({"error": str(exc)}, status=401)
        user = storage.get_or_create_user(uid)
        return web.json_response(serialize_user_for_webapp(user))

    async def handle_post_state(request: web.Request) -> web.Response:
        try:
            uid = _authenticate(request)
        except InitDataError as exc:
            return web.json_response({"error": str(exc)}, status=401)
        try:
            payload = await request.json()
        except ValueError:
            return web.json_response({"error": "Invalid JSON body"}, status=400)
        if not isinstance(payload, dict):
            return web.json_response({"error": "JSON object expected"}, status=400)
        user = storage.apply_webapp_settings(uid, payload)
        return web.json_response(serialize_user_for_webapp(user))

    async def handle_verify(request: web.Request) -> web.Response:
        try:
            uid = _authenticate(request)
        except InitDataError as exc:
            return web.json_response({"error": str(exc)}, status=401)
        try:
            payload = await request.json()
        except ValueError:
            return web.json_response({"error": "Invalid JSON body"}, status=400)

        user = storage.get_or_create_user(uid)
        god_name = str(payload.get("god_name") or user.god_name or "").strip()
        api_token = str(payload.get("api_token") or user.api_token or "").strip()
        if not god_name or not api_token:
            return web.json_response(
                {"error": "Укажите имя бога и API-токен"}, status=400
            )
        try:
            hero_payload = await client.fetch_hero(
                god_name, api_token, base_url=user.base_url
            )
        except GodvilleApiError as exc:
            return web.json_response({"error": str(exc)}, status=400)

        updated = storage.set_credentials(uid, god_name, api_token)
        encounter = analyze_hero_state(hero_payload)
        return web.json_response(
            {
                **serialize_user_for_webapp(updated),
                "has_private_fields": encounter.has_private_fields,
                "hero": {
                    "name": encounter.hero_name,
                    "level": encounter.hero_level,
                    "health": encounter.health,
                    "max_health": encounter.max_health,
                    "fight_type": encounter.fight_type,
                    "diary_last": encounter.diary_last,
                },
            }
        )

    async def handle_options(_: web.Request) -> web.Response:
        return web.Response(status=204)

    app.router.add_get("/health", handle_health)
    app.router.add_get("/api/state", handle_get_state)
    app.router.add_post("/api/state", handle_post_state)
    app.router.add_post("/api/verify", handle_verify)
    app.router.add_route("OPTIONS", "/api/{path:.*}", handle_options)

    if resolved_dir.is_dir():
        async def handle_index(_: web.Request) -> web.FileResponse:
            return web.FileResponse(resolved_dir / "index.html")

        app.router.add_get("/", handle_index)
        app.router.add_static("/", resolved_dir)

    return app
