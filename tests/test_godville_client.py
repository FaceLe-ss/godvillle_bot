from __future__ import annotations

import httpx
import pytest

from godville_bot.godville_client import (
    GodvilleApiError,
    GodvilleClient,
    GodvilleNotFoundError,
    GodvilleRateLimitError,
)


async def test_client_builds_encoded_url_and_parses_json() -> None:
    captured_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_urls.append(str(request.url))
        return httpx.Response(200, json={"name": "Герой", "fight_type": "dungeon"})

    client = GodvilleClient(transport=httpx.MockTransport(handler))
    try:
        data = await client.fetch_hero("Бог Имени", "tok/123", base_url="https://godville.net")
        assert data["fight_type"] == "dungeon"
        assert (
            captured_urls[0]
            == "https://godville.net/gods/api/%D0%91%D0%BE%D0%B3%20%D0%98%D0%BC%D0%B5%D0%BD%D0%B8/tok%2F123"
        )
    finally:
        await client.close()


async def test_client_handles_404_and_429() -> None:
    def handler_404(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="Not found")

    client_404 = GodvilleClient(transport=httpx.MockTransport(handler_404))
    try:
        with pytest.raises(GodvilleNotFoundError):
            await client_404.fetch_hero("MissingGod", "tok")
    finally:
        await client_404.close()

    def handler_429(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="Too many requests")

    client_429 = GodvilleClient(transport=httpx.MockTransport(handler_429))
    try:
        with pytest.raises(GodvilleRateLimitError):
            await client_429.fetch_hero("SomeGod", "tok")
    finally:
        await client_429.close()


async def test_client_handles_throttle_text_on_200() -> None:
    def handler_limit(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="Превышен лимит запросов к API")

    client = GodvilleClient(transport=httpx.MockTransport(handler_limit))
    try:
        with pytest.raises(GodvilleRateLimitError):
            await client.fetch_hero("SomeGod", "tok")
    finally:
        await client.close()

    def handler_500(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Server error")

    client_err = GodvilleClient(transport=httpx.MockTransport(handler_500))
    try:
        with pytest.raises(GodvilleApiError):
            await client_err.fetch_hero("SomeGod", "tok")
    finally:
        await client_err.close()
