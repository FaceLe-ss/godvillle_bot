from __future__ import annotations

import base64
import html
import json
import logging
from typing import Any
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    WebAppInfo,
)

from godville_bot.boss_parser import (
    ALL_FIGHT_TYPES,
    FIGHT_TYPE_LABELS,
    analyze_hero_state,
)
from godville_bot.godville_client import (
    GodvilleApiError,
    GodvilleClient,
    GodvilleNotFoundError,
    GodvilleRateLimitError,
)
from godville_bot.storage import BotStorage, UserConfig
from godville_bot.web_server import serialize_user_for_webapp

logger = logging.getLogger(__name__)

FILTER_MODE_LABELS: dict[str, str] = {
    "smart": "Умный (имя ИЛИ уровень; всё если пусто)",
    "strict": "Строгий (только совпадение фильтра)",
    "all": "Все боссы (+ пометка совпадений)",
}


class BotStates(StatesGroup):
    waiting_god_name = State()
    waiting_api_token = State()
    waiting_boss_names = State()


def _mask_token(token: str | None) -> str:
    if not token:
        return "не задан"
    if len(token) <= 6:
        return "***"
    return f"{token[:3]}***{token[-3:]}"


def _format_user_summary(user: UserConfig) -> str:
    status_icon = "🟢 Активен" if user.enabled else "⏸ На паузе"
    god = html.escape(user.god_name) if user.god_name else "<i>не привязан</i>"
    token_str = html.escape(_mask_token(user.api_token))
    fight_labels = ", ".join(
        FIGHT_TYPE_LABELS.get(ft, ft) for ft in user.fight_types
    ) or "<i>не выбраны</i>"
    names_str = (
        ", ".join(html.escape(n) for n in user.name_filters)
        if user.name_filters
        else "<i>не заданы</i>"
    )
    levels_str = (
        ", ".join(f"{lvl} ур." for lvl in user.level_filters)
        if user.level_filters
        else "<i>не заданы</i>"
    )
    mode_label = FILTER_MODE_LABELS.get(user.filter_mode, user.filter_mode)
    unknown_str = "Вкл" if user.notify_unknown_entry else "Выкл"

    return (
        f"⚙️ <b>Настройки отслеживания</b>\n"
        f"• <b>Мониторинг:</b> {status_icon}\n"
        f"• <b>Бог:</b> {god} (токен: <code>{token_str}</code>)\n"
        f"• <b>Типы боёв:</b> {fight_labels}\n"
        f"• <b>Фильтр по имени:</b> {names_str}\n"
        f"• <b>Фильтр по уровню:</b> {levels_str}\n"
        f"• <b>Режим фильтра:</b> {html.escape(mode_label)}\n"
        f"• <b>Сигнал при входе без деталей:</b> {unknown_str}\n\n"
        f"<i>Логика: срабатывает при совпадении имени ИЛИ уровня босса.</i>"
    )


def _build_webapp_url_with_state(base_webapp_url: str, user: UserConfig) -> str:
    """Attach sanitized non-secret user settings in ?state= for static sendData Mini App hosting."""
    parsed = urlparse(base_webapp_url)
    query_items = dict(parse_qsl(parsed.query, keep_blank_values=True))
    # If ?api= is explicitly set, Mini App loads live state from that API backend instead.
    if "api" not in query_items:
        state_json = json.dumps(serialize_user_for_webapp(user), ensure_ascii=False).encode("utf-8")
        encoded = base64.urlsafe_b64encode(state_json).decode("ascii").rstrip("=")
        query_items["state"] = encoded
    new_query = urlencode(query_items)
    return urlunparse(parsed._replace(query=new_query))


def _uses_send_data_mode(webapp_url: str) -> bool:
    parsed = urlparse(webapp_url)
    query_items = dict(parse_qsl(parsed.query, keep_blank_values=True))
    return parsed.netloc.endswith("github.io") and "api" not in query_items


def build_settings_keyboard(
    user: UserConfig, *, webapp_url: str | None = None
) -> InlineKeyboardMarkup:
    level_buttons = [
        InlineKeyboardButton(
            text=f"{'✅ ' if lvl in user.level_filters else ''}{lvl} ур.",
            callback_data=f"lvl:{lvl}",
        )
        for lvl in (1, 2, 3, 4)
    ]

    fight_rows: list[list[InlineKeyboardButton]] = []
    current_row: list[InlineKeyboardButton] = []
    for ft in ALL_FIGHT_TYPES:
        active = ft in user.fight_types
        label = FIGHT_TYPE_LABELS.get(ft, ft)
        current_row.append(
            InlineKeyboardButton(
                text=f"{'✅ ' if active else '▫️ '}{label}",
                callback_data=f"ft:{ft}",
            )
        )
        if len(current_row) == 2:
            fight_rows.append(current_row)
            current_row = []
    if current_row:
        fight_rows.append(current_row)

    mode_buttons = [
        InlineKeyboardButton(
            text=f"{'✅ ' if user.filter_mode == 'smart' else ''}Умный",
            callback_data="mode:smart",
        ),
        InlineKeyboardButton(
            text=f"{'✅ ' if user.filter_mode == 'strict' else ''}Строгий",
            callback_data="mode:strict",
        ),
        InlineKeyboardButton(
            text=f"{'✅ ' if user.filter_mode == 'all' else ''}Все боссы",
            callback_data="mode:all",
        ),
    ]

    rows: list[list[InlineKeyboardButton]] = [
        level_buttons,
        *fight_rows,
        mode_buttons,
        [
            InlineKeyboardButton(
                text="➕ Добавить имя босса",
                callback_data="action:addname",
            ),
            InlineKeyboardButton(
                text="🗑 Очистить имена",
                callback_data="action:clearnames",
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"{'✅ ' if user.notify_unknown_entry else '▫️ '}Сигнал входа без деталей",
                callback_data="action:toggle_unknown",
            ),
            InlineKeyboardButton(
                text="⏸ Пауза" if user.enabled else "▶️ Включить",
                callback_data="action:toggle_enabled",
            ),
        ],
        [
            InlineKeyboardButton(
                text="🔗 Привязать / сменить героя",
                callback_data="action:setup",
            ),
            InlineKeyboardButton(
                text="🔄 Проверить сейчас",
                callback_data="action:check_now",
            ),
        ],
    ]
    if webapp_url:
        if _uses_send_data_mode(webapp_url):
            rows.append(
                [
                    InlineKeyboardButton(
                        text="📱 Открыть Mini App (фильтры)",
                        callback_data="action:open_webapp",
                    )
                ]
            )
        else:
            rows.append(
                [
                    InlineKeyboardButton(
                        text="📱 Открыть Mini App (фильтры)",
                        web_app=WebAppInfo(url=webapp_url),
                    )
                ]
            )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def create_router(
    *,
    storage: BotStorage,
    client: GodvilleClient,
    allowed_telegram_ids: frozenset[int] = frozenset(),
    default_god_name: str | None = None,
    default_godville_token: str | None = None,
    webapp_url: str | None = None,
) -> Router:
    router = Router()

    def _is_allowed(user_id: int | None) -> bool:
        if not allowed_telegram_ids:
            return True
        return user_id is not None and user_id in allowed_telegram_ids

    def _kb(user: UserConfig) -> InlineKeyboardMarkup:
        return build_settings_keyboard(user, webapp_url=webapp_url)

    async def _send_webapp_launcher(message: Message, user: UserConfig) -> None:
        if not webapp_url:
            await message.answer(
                "📱 Mini App ещё не подключён.\n"
                "Укажите HTTPS-адрес в переменной <code>WEBAPP_URL</code> в <code>.env</code> "
                "(например, GitHub Pages или адрес вашего сервера/Cloudflare Worker)."
            )
            return

        if _uses_send_data_mode(webapp_url):
            launch_url = _build_webapp_url_with_state(webapp_url, user)
            reply_kb = ReplyKeyboardMarkup(
                keyboard=[
                    [
                        KeyboardButton(
                            text="📱 Настроить фильтры в Mini App",
                            web_app=WebAppInfo(url=launch_url),
                        )
                    ]
                ],
                resize_keyboard=True,
                one_time_keyboard=True,
            )
            await message.answer(
                "Нажмите кнопку ниже под полем ввода, чтобы открыть Mini App с текущими фильтрами:",
                reply_markup=reply_kb,
            )
            return

        inline_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📱 Открыть Mini App",
                        web_app=WebAppInfo(url=webapp_url),
                    )
                ]
            ]
        )
        await message.answer(
            "Откройте Mini App для настройки фильтров и привязки героя:",
            reply_markup=inline_kb,
        )

    async def _guard_message(message: Message) -> int | None:
        uid = message.from_user.id if message.from_user else None
        if not _is_allowed(uid):
            await message.answer("⛔ Доступ к этому боту ограничен.")
            return None
        assert uid is not None
        return uid

    async def _guard_callback(callback: CallbackQuery) -> int | None:
        uid = callback.from_user.id if callback.from_user else None
        if not _is_allowed(uid):
            await callback.answer("⛔ Доступ к этому боту ограничен.", show_alert=True)
            return None
        assert uid is not None
        return uid

    async def _verify_and_save_credentials(
        message: Message,
        user_id: int,
        god_name: str,
        api_token: str,
    ) -> None:
        base_url = storage.get_or_create_user(user_id).base_url
        try:
            payload = await client.fetch_hero(god_name, api_token, base_url=base_url)
        except GodvilleNotFoundError:
            await message.answer(
                f"❌ Бог <b>{html.escape(god_name)}</b> не найден на <code>{html.escape(base_url)}</code>.\n"
                "Проверьте точное написание имени бога (с учётом регистра)."
            )
            return
        except GodvilleRateLimitError:
            await message.answer(
                "⏳ Годвилль временно ограничил частоту запросов. Попробуйте снова через минуту."
            )
            return
        except GodvilleApiError as exc:
            await message.answer(f"❌ Ошибка при проверке API Годвилля: <code>{html.escape(str(exc))}</code>")
            return

        encounter = analyze_hero_state(payload)
        user = storage.set_credentials(user_id, god_name, api_token)

        if not encounter.has_private_fields:
            await message.answer(
                "⚠️ <b>Бог найден, но приватные поля не получены!</b>\n"
                "Проверьте, что вы скопировали актуальный секретный API-токен из профиля на сайте Годвилля "
                "(иначе поля <code>fight_type</code> и <code>diary_last</code> будут недоступны).\n\n"
                + _format_user_summary(user),
                reply_markup=_kb(user),
            )
            return

        hero_line = f"{html.escape(encounter.hero_name)}"
        if encounter.hero_level is not None:
            hero_line += f" ({encounter.hero_level} ур.)"
        await message.answer(
            f"✅ <b>Герой успешно привязан:</b> {hero_line}\n\n"
            + _format_user_summary(user),
            reply_markup=_kb(user),
        )

    @router.message(Command("start"))
    async def cmd_start(message: Message, state: FSMContext) -> None:
        uid = await _guard_message(message)
        if uid is None:
            return
        await state.clear()
        user = storage.get_or_create_user(uid)

        # Optional one-time bootstrap from environment variables if user isn't linked yet.
        if (
            not user.god_name
            and default_god_name
            and default_godville_token
        ):
            user = storage.set_credentials(uid, default_god_name, default_godville_token)

        intro = (
            "👋 <b>Бот уведомлений о боссах Годвилля</b>\n\n"
            "Отслеживаю вашего героя через официальный приватный API и присылаю уведомление "
            "при встрече с боссом <b>по нужному имени ИЛИ нужному уровню (1–4)</b>.\n\n"
            "<b>Быстрый старт:</b>\n"
            "1. Скопируйте секретный API-токен в профиле на <code>godville.net</code>.\n"
            "2. Выполните <code>/setup ИмяБога ВашТокен</code> (или нажмите кнопку ниже).\n"
            "3. Задайте имена (<code>/addname Днищеброд, Великотушный</code>) и уровни (кнопками или <code>/levels 2 3</code>).\n\n"
            + _format_user_summary(user)
        )
        await message.answer(intro, reply_markup=_kb(user))

    @router.message(Command("app"))
    async def cmd_app(message: Message) -> None:
        uid = await _guard_message(message)
        if uid is None:
            return
        user = storage.get_or_create_user(uid)
        await _send_webapp_launcher(message, user)

    @router.message(F.web_app_data)
    async def handle_web_app_data(message: Message) -> None:
        uid = await _guard_message(message)
        if uid is None or not message.web_app_data:
            return
        try:
            payload = json.loads(message.web_app_data.data)
        except ValueError:
            await message.answer("❌ Не удалось прочитать данные из Mini App.")
            return
        if not isinstance(payload, dict):
            await message.answer("❌ Неверный формат настроек из Mini App.")
            return
        user = storage.apply_webapp_settings(uid, payload)
        await message.answer(
            "✅ <b>Настройки из Mini App сохранены!</b>",
            reply_markup=ReplyKeyboardRemove(),
        )
        await message.answer(_format_user_summary(user), reply_markup=_kb(user))

    @router.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        uid = await _guard_message(message)
        if uid is None:
            return
        await message.answer(
            "📘 <b>Команды бота</b>\n\n"
            "• <code>/setup ИмяБога Токен</code> — привязать героя к приватному API\n"
            "• <code>/app</code> — открыть Mini App для настройки фильтров\n"
            "• <code>/filters</code> (или <code>/settings</code>) — открыть панель фильтров\n"
            "• <code>/addname Имя1, Имя2</code> — добавить боссов в фильтр по имени\n"
            "• <code>/delname Имя</code> — удалить имя из фильтра\n"
            "• <code>/clearnames</code> — очистить все имена\n"
            "• <code>/levels 1 2 3</code> — фильтровать по уровням/абилкам (<code>/levels clear</code> для сброса)\n"
            "• <code>/status</code> — текущие настройки и мгновенная проверка героя\n"
            "• <code>/pause</code> / <code>/resume</code> — пауза / возобновление мониторинга\n\n"
            "ℹ️ <b>Как работает распознавание по API:</b>\n"
            "Сервер Годвилля обновляет JSON раз в минуту и не отдаёт отдельные поля с именем и уровнем текущего врага. "
            "Бот определяет бой по <code>fight_type</code> и разбирает <code>diary_last</code>: распознаёт каталог боссов "
            "подземелий 1–4 ур., префиксы способностей и явные упоминания уровня. Склонения русских имён учитываются."
        )

    @router.message(Command("setup"))
    async def cmd_setup(message: Message, command: CommandObject, state: FSMContext) -> None:
        uid = await _guard_message(message)
        if uid is None:
            return
        args = (command.args or "").strip()
        if not args:
            await state.set_state(BotStates.waiting_god_name)
            await message.answer("Введите точное <b>имя вашего бога</b> в Годвилле:")
            return

        parts = args.split()
        if len(parts) < 2:
            await message.answer(
                "Укажите оба параметра через пробел (если имя бога из нескольких слов, "
                "проще запустить пошагово командой <code>/setup</code> без аргументов):\n"
                "<code>/setup ИмяБога API_Токен</code>"
            )
            return

        api_token = parts[-1]
        god_name = " ".join(parts[:-1])
        await _verify_and_save_credentials(message, uid, god_name, api_token)

    @router.message(BotStates.waiting_god_name)
    async def fsm_god_name(message: Message, state: FSMContext) -> None:
        uid = await _guard_message(message)
        if uid is None:
            return
        god_name = (message.text or "").strip()
        if not god_name or god_name.startswith("/"):
            await message.answer("Пожалуйста, введите имя бога текстом (без '/').")
            return
        await state.update_data(god_name=god_name)
        await state.set_state(BotStates.waiting_api_token)
        await message.answer(
            f"Бог: <b>{html.escape(god_name)}</b>.\n"
            "Теперь отправьте <b>секретный API-токен</b> из профиля на сайте Годвилля:"
        )

    @router.message(BotStates.waiting_api_token)
    async def fsm_api_token(message: Message, state: FSMContext) -> None:
        uid = await _guard_message(message)
        if uid is None:
            return
        api_token = (message.text or "").strip()
        if not api_token or api_token.startswith("/"):
            await message.answer("Отправьте токен строкой (без '/').")
            return
        data: dict[str, Any] = await state.get_data()
        god_name = str(data.get("god_name", "")).strip()
        await state.clear()
        if not god_name:
            await message.answer("Не найдено имя бога, начните заново через /setup.")
            return
        await _verify_and_save_credentials(message, uid, god_name, api_token)

    @router.message(BotStates.waiting_boss_names)
    async def fsm_boss_names(message: Message, state: FSMContext) -> None:
        uid = await _guard_message(message)
        if uid is None:
            return
        raw = (message.text or "").strip()
        await state.clear()
        if not raw or raw.startswith("/"):
            await message.answer("Добавление отменено.")
            return
        names = [part.strip() for part in raw.split(",") if part.strip()]
        user = storage.add_name_filters(uid, names)
        await message.answer(
            "✅ Имена добавлены в фильтр.\n\n" + _format_user_summary(user),
            reply_markup=_kb(user),
        )

    @router.message(Command("filters", "settings"))
    async def cmd_filters(message: Message) -> None:
        uid = await _guard_message(message)
        if uid is None:
            return
        user = storage.get_or_create_user(uid)
        await message.answer(
            _format_user_summary(user),
            reply_markup=_kb(user),
        )

    @router.message(Command("addname"))
    async def cmd_addname(message: Message, command: CommandObject) -> None:
        uid = await _guard_message(message)
        if uid is None:
            return
        raw = (command.args or "").strip()
        if not raw:
            await message.answer("Укажите имя босса (или несколько через запятую): <code>/addname Днищеброд, Великотушный</code>")
            return
        names = [part.strip() for part in raw.split(",") if part.strip()]
        user = storage.add_name_filters(uid, names)
        await message.answer(
            "✅ Фильтр имён обновлён.\n\n" + _format_user_summary(user),
            reply_markup=_kb(user),
        )

    @router.message(Command("delname"))
    async def cmd_delname(message: Message, command: CommandObject) -> None:
        uid = await _guard_message(message)
        if uid is None:
            return
        raw = (command.args or "").strip()
        if not raw:
            await message.answer("Укажите имя для удаления: <code>/delname Днищеброд</code>")
            return
        user, removed = storage.remove_name_filter(uid, raw)
        prefix = "✅ Удалено." if removed else "ℹ️ Такого имени не было в фильтре."
        await message.answer(
            f"{prefix}\n\n" + _format_user_summary(user),
            reply_markup=_kb(user),
        )

    @router.message(Command("clearnames"))
    async def cmd_clearnames(message: Message) -> None:
        uid = await _guard_message(message)
        if uid is None:
            return
        user = storage.clear_name_filters(uid)
        await message.answer(
            "🗑 Список имён очищен.\n\n" + _format_user_summary(user),
            reply_markup=_kb(user),
        )

    @router.message(Command("levels"))
    async def cmd_levels(message: Message, command: CommandObject) -> None:
        uid = await _guard_message(message)
        if uid is None:
            return
        raw = (command.args or "").strip().lower()
        if not raw:
            await message.answer("Укажите уровни от 1 до 4 через пробел или запятую, либо <code>clear</code>:\n<code>/levels 2 3</code>")
            return
        if raw in ("clear", "reset", "none", "очистить", "сброс"):
            user = storage.set_level_filters(uid, [])
            await message.answer(
                "🗑 Фильтр уровней очищен.\n\n" + _format_user_summary(user),
                reply_markup=_kb(user),
            )
            return

        tokens = raw.replace(",", " ").split()
        parsed_levels: list[int] = []
        for tok in tokens:
            if tok.isdigit() and int(tok) in (1, 2, 3, 4):
                parsed_levels.append(int(tok))
            else:
                await message.answer("❌ Допустимы только уровни 1, 2, 3 или 4.")
                return
        user = storage.set_level_filters(uid, parsed_levels)
        await message.answer(
            "✅ Фильтр уровней обновлён.\n\n" + _format_user_summary(user),
            reply_markup=_kb(user),
        )

    @router.message(Command("pause"))
    async def cmd_pause(message: Message) -> None:
        uid = await _guard_message(message)
        if uid is None:
            return
        user = storage.set_enabled(uid, False)
        await message.answer("⏸ Мониторинг поставлен на паузу.", reply_markup=_kb(user))

    @router.message(Command("resume"))
    async def cmd_resume(message: Message) -> None:
        uid = await _guard_message(message)
        if uid is None:
            return
        user = storage.set_enabled(uid, True)
        await message.answer("▶️ Мониторинг возобновлён.", reply_markup=_kb(user))

    async def _send_live_status(target_message: Message, user: UserConfig) -> None:
        summary = _format_user_summary(user)
        if not user.god_name or not user.api_token:
            await target_message.answer(
                summary + "\n\n⚠️ Герой ещё не привязан. Используйте <code>/setup ИмяБога Токен</code>.",
                reply_markup=_kb(user),
            )
            return

        try:
            payload = await client.fetch_hero(user.god_name, user.api_token, base_url=user.base_url)
        except GodvilleApiError as exc:
            await target_message.answer(
                summary + f"\n\n⚠️ Ошибка опроса API: <code>{html.escape(str(exc))}</code>",
                reply_markup=_kb(user),
            )
            return

        encounter = analyze_hero_state(payload)
        hp_part = (
            f"{encounter.health}/{encounter.max_health}"
            if encounter.health is not None and encounter.max_health is not None
            else "?"
        )
        fight_label = (
            FIGHT_TYPE_LABELS.get(encounter.fight_type or "", encounter.fight_type or "нет")
            if encounter.fight_type
            else "обычное приключение"
        )
        live_lines = [
            f"📊 <b>Текущее состояние:</b> {html.escape(encounter.hero_name)} ({encounter.hero_level or '?'} ур., HP {hp_part})",
            f"• <b>Режим боя:</b> {html.escape(fight_label)}",
        ]
        if encounter.boss_name or encounter.boss_level:
            boss_desc = html.escape(encounter.boss_name or "не распознан")
            if encounter.boss_level is not None:
                boss_desc += f" ({encounter.boss_level} ур.)"
            live_lines.append(f"• <b>Обнаружен босс:</b> {boss_desc}")
        if not encounter.has_private_fields:
            live_lines.append("• ⚠️ <i>Приватные поля недоступны — проверьте API-токен!</i>")
        if encounter.diary_last:
            live_lines.append(f"• <b>Дневник:</b> <i>{html.escape(encounter.diary_last)}</i>")

        await target_message.answer(
            summary + "\n\n" + "\n".join(live_lines),
            reply_markup=_kb(user),
        )

    @router.message(Command("status"))
    async def cmd_status(message: Message) -> None:
        uid = await _guard_message(message)
        if uid is None:
            return
        user = storage.get_or_create_user(uid)
        await _send_live_status(message, user)

    async def _safe_edit_settings(callback: CallbackQuery, user: UserConfig) -> None:
        if not callback.message:
            return
        try:
            await callback.message.edit_text(
                _format_user_summary(user),
                reply_markup=_kb(user),
            )
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc).casefold():
                raise

    @router.callback_query(F.data.startswith("lvl:"))
    async def cb_toggle_level(callback: CallbackQuery) -> None:
        uid = await _guard_callback(callback)
        if uid is None:
            return
        lvl = int((callback.data or "lvl:1").split(":")[1])
        user = storage.toggle_level_filter(uid, lvl)
        await _safe_edit_settings(callback, user)
        await callback.answer(f"Уровень {lvl} переключён")

    @router.callback_query(F.data.startswith("ft:"))
    async def cb_toggle_fight_type(callback: CallbackQuery) -> None:
        uid = await _guard_callback(callback)
        if uid is None:
            return
        ft = (callback.data or "").split(":", 1)[1]
        if ft not in ALL_FIGHT_TYPES:
            await callback.answer("Неизвестный тип боя", show_alert=True)
            return
        user = storage.toggle_fight_type(uid, ft)
        await _safe_edit_settings(callback, user)
        await callback.answer(f"{FIGHT_TYPE_LABELS.get(ft, ft)} переключён")

    @router.callback_query(F.data.startswith("mode:"))
    async def cb_set_mode(callback: CallbackQuery) -> None:
        uid = await _guard_callback(callback)
        if uid is None:
            return
        mode = (callback.data or "").split(":", 1)[1]
        user = storage.set_filter_mode(uid, mode)
        await _safe_edit_settings(callback, user)
        await callback.answer("Режим фильтрации обновлён")

    @router.callback_query(F.data.startswith("action:"))
    async def cb_action(callback: CallbackQuery, state: FSMContext) -> None:
        uid = await _guard_callback(callback)
        if uid is None:
            return
        action = (callback.data or "").split(":", 1)[1]

        if action == "addname":
            await state.set_state(BotStates.waiting_boss_names)
            if callback.message:
                await callback.message.answer(
                    "Введите имя босса для фильтра (или несколько через запятую), например:\n"
                    "<code>Днищеброд, Великотушный</code>"
                )
            await callback.answer()
            return

        if action == "clearnames":
            user = storage.clear_name_filters(uid)
            await _safe_edit_settings(callback, user)
            await callback.answer("Список имён очищен")
            return

        if action == "toggle_unknown":
            user = storage.toggle_notify_unknown(uid)
            await _safe_edit_settings(callback, user)
            await callback.answer("Переключено")
            return

        if action == "toggle_enabled":
            cur = storage.get_or_create_user(uid)
            user = storage.set_enabled(uid, not cur.enabled)
            await _safe_edit_settings(callback, user)
            await callback.answer("Мониторинг включён" if user.enabled else "Мониторинг на паузе")
            return

        if action == "setup":
            await state.set_state(BotStates.waiting_god_name)
            if callback.message:
                await callback.message.answer("Введите точное <b>имя вашего бога</b> в Годвилле:")
            await callback.answer()
            return

        if action == "check_now":
            user = storage.get_or_create_user(uid)
            await callback.answer("Запрашиваю API Годвилля...")
            if callback.message:
                await _send_live_status(callback.message, user)
            return

        if action == "open_webapp":
            user = storage.get_or_create_user(uid)
            await callback.answer()
            if callback.message:
                await _send_webapp_launcher(callback.message, user)
            return

        await callback.answer()

    return router
