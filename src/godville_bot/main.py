from __future__ import annotations

import asyncio
import logging

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo

from godville_bot.config import Settings
from godville_bot.godville_client import GodvilleClient
from godville_bot.handlers import _uses_send_data_mode, create_router
from godville_bot.notifier import BossMonitorService
from godville_bot.storage import BotStorage
from godville_bot.web_server import create_web_app

logger = logging.getLogger(__name__)


async def _set_bot_commands(bot: Bot, webapp_url: str | None) -> None:
    commands = [
        BotCommand(command="start", description="Запуск и быстрая настройка"),
        BotCommand(command="setup", description="Привязать бога и API-токен"),
        BotCommand(command="app", description="Открыть Mini App настроек"),
        BotCommand(command="filters", description="Настройки и фильтры боссов"),
        BotCommand(command="addname", description="Добавить имя босса в фильтр"),
        BotCommand(command="delname", description="Удалить имя босса из фильтра"),
        BotCommand(command="levels", description="Установить фильтр по уровням (1-4)"),
        BotCommand(command="status", description="Статус и проверка героя сейчас"),
        BotCommand(command="pause", description="Поставить мониторинг на паузу"),
        BotCommand(command="resume", description="Возобновить мониторинг"),
        BotCommand(command="help", description="Справка и ограничения API"),
    ]
    await bot.set_my_commands(commands)

    if webapp_url and not _uses_send_data_mode(webapp_url):
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Фильтры",
                web_app=WebAppInfo(url=webapp_url),
            )
        )


async def run_bot(settings: Settings) -> None:
    storage = BotStorage(settings.db_path, default_base_url=settings.godville_base_url)
    client = GodvilleClient(timeout_seconds=settings.request_timeout_seconds)
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    router = create_router(
        storage=storage,
        client=client,
        allowed_telegram_ids=settings.allowed_telegram_ids,
        default_god_name=settings.default_god_name,
        default_godville_token=settings.default_godville_token,
        webapp_url=settings.webapp_url,
    )
    dp.include_router(router)

    async def send_telegram_message(chat_id: int, text: str) -> None:
        await bot.send_message(chat_id=chat_id, text=text)

    monitor = BossMonitorService(
        storage=storage,
        client=client,
        send_message=send_telegram_message,
        poll_interval_seconds=settings.poll_interval_seconds,
    )

    stop_event = asyncio.Event()
    monitor_task: asyncio.Task[None] | None = None
    web_runner: web.AppRunner | None = None

    try:
        if settings.web_port > 0:
            web_app = create_web_app(
                bot_token=settings.bot_token,
                storage=storage,
                client=client,
                allowed_telegram_ids=settings.allowed_telegram_ids,
            )
            web_runner = web.AppRunner(web_app)
            await web_runner.setup()
            site = web.TCPSite(web_runner, host=settings.web_host, port=settings.web_port)
            await site.start()
            logger.info("Mini App & API server listening on http://%s:%s", settings.web_host, settings.web_port)

        await _set_bot_commands(bot, settings.webapp_url)
        monitor_task = asyncio.create_task(monitor.run_forever(stop_event))
        logger.info("Bot started. Starting Telegram polling...")
        await dp.start_polling(bot)
    finally:
        stop_event.set()
        if monitor_task is not None:
            try:
                await monitor_task
            except Exception:
                logger.exception("Monitor task failed during shutdown")
        if web_runner is not None:
            await web_runner.cleanup()
        await client.close()
        await bot.session.close()
        storage.close()


def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    settings = Settings.from_env()
    asyncio.run(run_bot(settings))


if __name__ == "__main__":
    run()
