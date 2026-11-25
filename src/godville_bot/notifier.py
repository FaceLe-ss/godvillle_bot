from __future__ import annotations

import asyncio
import html
import logging
from typing import Awaitable, Callable

from godville_bot.boss_parser import (
    FIGHT_TYPE_LABELS,
    BossEncounter,
    FilterResult,
    analyze_hero_state,
    evaluate_filters,
    normalize_ru,
)
from godville_bot.godville_client import (
    GodvilleApiError,
    GodvilleClient,
    GodvilleNotFoundError,
    GodvilleRateLimitError,
)
from godville_bot.storage import BotStorage, UserConfig

logger = logging.getLogger(__name__)

SendMessageFn = Callable[[int, str], Awaitable[None]]


def compute_dedup_key(encounter: BossEncounter, filter_result: FilterResult | None = None) -> str:
    """Create a stable deduplication key for the current boss encounter."""
    fight = encounter.fight_type or ("arena" if encounter.arena_fight else "fight")
    if filter_result is not None and filter_result.reason == "unknown_fight_entry":
        return f"{fight}:entry"
    if encounter.boss_name:
        return f"{fight}:name:{normalize_ru(encounter.boss_name)}"
    if filter_result is not None and filter_result.matched_names:
        return f"{fight}:name:{normalize_ru(filter_result.matched_names[0])}"
    if encounter.boss_level is not None:
        return f"{fight}:lvl:{encounter.boss_level}"
    return f"{fight}:combat"


def format_encounter_message(encounter: BossEncounter, filter_result: FilterResult) -> str:
    """Format an HTML Telegram notification message for a boss encounter."""
    is_direct_hit = bool(filter_result.matched_names or filter_result.matched_levels)
    header = "🎯 <b>Встречен нужный босс!</b>" if is_direct_hit else "⚔️ <b>Встреча с боссом!</b>"

    fight_label = FIGHT_TYPE_LABELS.get(
        encounter.fight_type or "", encounter.fight_type or "Бой"
    )
    lines: list[str] = [
        header,
        f"• <b>Режим:</b> {html.escape(fight_label)}",
    ]

    display_boss_name = encounter.boss_name or (
        ", ".join(filter_result.matched_names) if filter_result.matched_names else None
    )
    if display_boss_name:
        lines.append(f"• <b>Босс:</b> {html.escape(display_boss_name)}")
    else:
        lines.append("• <b>Босс:</b> <i>имя не распознано в diary_last</i>")

    if encounter.boss_level is not None:
        lines.append(f"• <b>Уровень / абилки:</b> {encounter.boss_level}")

    if encounter.abilities:
        abilities_str = ", ".join(html.escape(a) for a in encounter.abilities)
        lines.append(f"• <b>Способности:</b> {abilities_str}")

    if is_direct_hit:
        reasons: list[str] = []
        if filter_result.matched_names:
            matched_n = ", ".join(html.escape(n) for n in filter_result.matched_names)
            reasons.append(f"имя ({matched_n})")
        if filter_result.matched_levels:
            matched_l = ", ".join(str(lvl) for lvl in filter_result.matched_levels)
            reasons.append(f"уровень ({matched_l})")
        lines.append(f"• <b>Совпадение:</b> {'; '.join(reasons)}")

    hero_bits = [html.escape(encounter.hero_name)]
    if encounter.hero_level is not None:
        hero_bits.append(f"{encounter.hero_level} ур.")
    if encounter.health is not None and encounter.max_health is not None:
        hero_bits.append(f"HP {encounter.health}/{encounter.max_health}")
    lines.append(f"• <b>Герой:</b> {', '.join(hero_bits)}")

    if encounter.quest:
        lines.append(f"• <b>Задание:</b> {html.escape(encounter.quest)}")

    if encounter.diary_last:
        lines.append(f"\n📖 <i>{html.escape(encounter.diary_last)}</i>")

    return "\n".join(lines)


class BossMonitorService:
    """Polls Godville API for active users and dispatches Telegram notifications."""

    def __init__(
        self,
        storage: BotStorage,
        client: GodvilleClient,
        send_message: SendMessageFn,
        *,
        poll_interval_seconds: int = 60,
        max_backoff_seconds: int = 600,
    ) -> None:
        self.storage = storage
        self.client = client
        self.send_message = send_message
        self.poll_interval_seconds = poll_interval_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self._user_backoff_until: dict[int, float] = {}
        self._user_failures: dict[int, int] = {}

    async def poll_user(self, user: UserConfig, *, now_monotonic: float | None = None) -> bool:
        """Poll Godville once for a single user. Returns True if a notification was sent."""
        if not user.god_name or not user.api_token:
            return False

        now = now_monotonic if now_monotonic is not None else asyncio.get_running_loop().time()
        backoff_until = self._user_backoff_until.get(user.telegram_id, 0.0)
        if now < backoff_until:
            return False

        try:
            payload = await self.client.fetch_hero(
                user.god_name,
                user.api_token,
                base_url=user.base_url,
            )
        except GodvilleRateLimitError as exc:
            failures = self._user_failures.get(user.telegram_id, 0) + 1
            self._user_failures[user.telegram_id] = failures
            delay = min(self.max_backoff_seconds, self.poll_interval_seconds * (2 ** min(failures, 4)))
            self._user_backoff_until[user.telegram_id] = now + delay
            logger.warning(
                "Rate limited for user %s (%s); backing off for %ss: %s",
                user.telegram_id,
                user.god_name,
                delay,
                exc,
            )
            return False
        except GodvilleNotFoundError as exc:
            logger.warning("God not found for user %s: %s", user.telegram_id, exc)
            return False
        except GodvilleApiError as exc:
            failures = self._user_failures.get(user.telegram_id, 0) + 1
            self._user_failures[user.telegram_id] = failures
            delay = min(self.max_backoff_seconds, 30 * (2 ** min(failures - 1, 3)))
            self._user_backoff_until[user.telegram_id] = now + delay
            logger.warning("Godville API error for user %s: %s", user.telegram_id, exc)
            return False

        self._user_failures.pop(user.telegram_id, None)
        self._user_backoff_until.pop(user.telegram_id, None)

        encounter = analyze_hero_state(payload)

        if not encounter.has_private_fields:
            if not user.token_warning_sent:
                await self.send_message(
                    user.telegram_id,
                    "⚠️ <b>Не удалось получить приватные данные Годвилля</b> "
                    "(<code>diary_last</code>, <code>fight_type</code>).\n"
                    "Возможно, API-токен в профиле Годвилля был сброшен или указан с ошибкой. "
                    "Обновите его командой <code>/setup ИмяБога НовыйТокен</code>.",
                )
            self.storage.update_poll_state(
                user.telegram_id,
                last_fight_type=None,
                last_diary=user.last_diary,
                last_notified_key=None,
                token_warning_sent=True,
            )
            return False

        # Reset warning flag once private data succeeds again.
        token_warning_flag = False if user.token_warning_sent else None

        is_fight_entry = bool(
            encounter.fight_type and encounter.fight_type != user.last_fight_type
        )
        filter_result = evaluate_filters(
            encounter,
            enabled_fight_types=user.fight_types,
            name_filters=list(user.name_filters),
            level_filters=list(user.level_filters),
            filter_mode=user.filter_mode,
            notify_unknown_entry=user.notify_unknown_entry,
            is_fight_entry=is_fight_entry,
        )

        # Reset dedup key when leaving a fight, after victory/defeat, or on non-combat exploration steps.
        if (
            not encounter.is_boss_fight
            or encounter.is_post_fight
            or (encounter.fight_type in ("dungeon", "sail") and not encounter.is_combat_signal)
        ):
            if not (user.notify_unknown_entry and user.last_notified_key == f"{encounter.fight_type}:entry" and encounter.fight_type == user.last_fight_type):
                next_notified_key: str | None = None
            else:
                next_notified_key = user.last_notified_key
        else:
            next_notified_key = user.last_notified_key

        notified_now = False
        if filter_result.should_notify:
            dedup_key = compute_dedup_key(encounter, filter_result)
            if dedup_key != user.last_notified_key:
                text = format_encounter_message(encounter, filter_result)
                await self.send_message(user.telegram_id, text)
                next_notified_key = dedup_key
                notified_now = True

        self.storage.update_poll_state(
            user.telegram_id,
            last_fight_type=encounter.fight_type,
            last_diary=encounter.diary_last or user.last_diary,
            last_notified_key=next_notified_key,
            notified_now=notified_now,
            token_warning_sent=token_warning_flag,
        )
        return notified_now

    async def poll_once(self) -> int:
        """Poll all active users once. Returns number of notifications sent."""
        users = self.storage.list_active_users()
        sent_count = 0
        for user in users:
            try:
                if await self.poll_user(user):
                    sent_count += 1
            except Exception:
                logger.exception("Unexpected error polling user %s", user.telegram_id)
        return sent_count

    async def run_forever(self, stop_event: asyncio.Event) -> None:
        """Run periodic Godville polling until stop_event is set."""
        logger.info("Starting Godville monitor loop (interval=%ss)", self.poll_interval_seconds)
        while not stop_event.is_set():
            await self.poll_once()
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.poll_interval_seconds)
            except asyncio.TimeoutError:
                continue
        logger.info("Godville monitor loop stopped")
