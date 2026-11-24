"""MoneyMate: entry point. Run with:  python bot.py"""
from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from app import config, context
from app.db import Database
from app.handlers import expenses, income, onboarding, reports, settings
from app.handlers.common import UserMiddleware
from app.i18n import t
from app.scheduler import scheduler_loop

COMMAND_KEYS = [
    ("start", "cmd.start"), ("add", "cmd.add"), ("income", "cmd.income"), ("today", "cmd.today"),
    ("month", "cmd.month"), ("show", "cmd.show"), ("categories", "cmd.categories"),
    ("balance", "cmd.balance"), ("stats", "cmd.stats"), ("chart", "cmd.chart"),
    ("export", "cmd.export"), ("undo", "cmd.undo"), ("settings", "cmd.settings"),
    ("help", "cmd.help"),
]


async def set_commands(bot: Bot) -> None:
    """Show the command menu in each language (Telegram picks it by the user's app language)."""
    for lang in config.LANGUAGES:
        commands = [BotCommand(command=c, description=t(lang, key)) for c, key in COMMAND_KEYS]
        await bot.set_my_commands(commands, language_code=lang)
    await bot.set_my_commands([BotCommand(command=c, description=t("en", key)) for c, key in COMMAND_KEYS])


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not config.BOT_TOKEN:
        sys.exit("BOT_TOKEN is not set. Copy .env.example to .env and put your token from @BotFather in it.")

    db = Database(config.DB_PATH)
    context.set_db(db)

    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.outer_middleware(UserMiddleware())

    # Order matters: specific flows first, the free-text catch-all (in `expenses`) last.
    dp.include_router(onboarding.router)
    dp.include_router(settings.router)
    dp.include_router(income.router)
    dp.include_router(reports.router)
    dp.include_router(expenses.router)

    await set_commands(bot)
    me = await bot.get_me()
    logging.info("Bot started as @%s", me.username)

    scheduler = asyncio.create_task(scheduler_loop(bot, db))
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.cancel()
        await bot.session.close()
        db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
