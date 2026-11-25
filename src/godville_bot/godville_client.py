from __future__ import annotations

import asyncio
import time
from typing import Any
from urllib.parse import quote

import httpx


class GodvilleApiError(Exception):
    """Base error raised when querying the Godville API."""


class GodvilleNotFoundError(GodvilleApiError):
    """Raised when the specified god name is not found (HTTP 404)."""


class GodvilleRateLimitError(GodvilleApiError):
    """Raised when Godville rate-limits requests (HTTP 429 or throttling text)."""


class GodvilleClient:
    """Async HTTP client for Godville's official JSON API."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 15.0,
        min_request_interval: float = 0.0,
        transport: httpx.AsyncBaseTransport | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=timeout_seconds,
            headers={
                "User-Agent": "GodvilleBossTelegramBot/0.1 (+https://godville.net)",
                "Accept": "application/json",
            },
            transport=transport,
            follow_redirects=True,
        )
        self._min_request_interval = max(0.0, min_request_interval)
        self._last_request_at: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @staticmethod
    def build_api_url(god_name: str, api_token: str | None, base_url: str) -> str:
        clean_base = base_url.rstrip("/")
        encoded_god = quote(god_name.strip(), safe="")
        if api_token and api_token.strip():
            encoded_token = quote(api_token.strip(), safe="")
            return f"{clean_base}/gods/api/{encoded_god}/{encoded_token}"
        return f"{clean_base}/gods/api/{encoded_god}"

    async def _respect_rate_limit(self, key: str) -> None:
        if self._min_request_interval <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            prev = self._last_request_at.get(key)
            if prev is not None:
                wait_for = self._min_request_interval - (now - prev)
                if wait_for > 0:
                    await asyncio.sleep(wait_for)
            self._last_request_at[key] = time.monotonic()

    async def fetch_hero(
        self,
        god_name: str,
        api_token: str | None,
        base_url: str = "https://godville.net",
    ) -> dict[str, Any]:
        if not god_name or not god_name.strip():
            raise ValueError("god_name must not be empty")

        url = self.build_api_url(god_name, api_token, base_url)
        await self._respect_rate_limit(f"{base_url}:{god_name.strip().casefold()}")

        try:
            response = await self._client.get(url)
        except httpx.HTTPError as exc:
            raise GodvilleApiError(f"Network error contacting Godville API: {exc}") from exc

        if response.status_code == 404:
            raise GodvilleNotFoundError(f"God '{god_name}' was not found on {base_url}")
        if response.status_code == 429:
            raise GodvilleRateLimitError("Godville API rate limit exceeded (HTTP 429)")
        if response.status_code >= 400:
            raise GodvilleApiError(
                f"Godville API returned HTTP {response.status_code}: {response.text[:200]}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            body_preview = response.text[:200].strip()
            if "limit" in body_preview.casefold() or "лимит" in body_preview.casefold():
                raise GodvilleRateLimitError(f"Godville API throttled: {body_preview}") from exc
            raise GodvilleApiError(f"Invalid JSON from Godville API: {body_preview}") from exc

        if not isinstance(data, dict):
            raise GodvilleApiError("Unexpected non-object JSON payload from Godville API")
        return data
