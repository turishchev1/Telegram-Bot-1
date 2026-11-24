"""Background jobs: daily tips, monthly reports and logging reminders.

One job runs every minute and asks the database who is due (see due.py), so each person
gets messages at *their* local time and nothing is sent twice, even after a restart."""
from __future__ import annotations

import asyncio
import html
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from . import service, tips
from .db import Database
from .due import users_due_for_reminder, users_due_for_report, users_due_for_tip
from .handlers.reports import send_monthly_report
from .i18n import t

log = logging.getLogger(__name__)

TICK_SECONDS = 60


async def _safe(coro, db: Database, user) -> bool:
    """Run a send; returns False if the user blocked the bot (their tips are switched off)."""
    try:
        await coro
        return True
    except TelegramForbiddenError:
        log.info("user %s blocked the bot; disabling their messages", user["telegram_id"])
        service.update_user(db, user["telegram_id"], tips_enabled=0, reminders_enabled=0)
    except TelegramRetryAfter as exc:
        await asyncio.sleep(exc.retry_after)
    except Exception:
        log.exception("failed to send to %s", user["telegram_id"])
    return False


async def run_once(bot: Bot, db: Database) -> None:
    for u in users_due_for_tip(db):
        tip = tips.pick_tip(db, u, service.user_today(u))
        if tip is None:
            continue
        text = t(u["language"], "tips.card", text=html.escape(tips.tip_text(tip, u["language"]), quote=False))
        if await _safe(bot.send_message(u["telegram_id"], text), db, u):
            tips.mark_sent(db, u["telegram_id"], tip["id"])
            service.update_user(db, u["telegram_id"], last_tip_date=service.user_today(u).isoformat())
        await asyncio.sleep(0.05)  # stay far below Telegram's ~30 messages/second limit

    for u, first, last in users_due_for_report(db):
        await _safe(send_monthly_report(bot, db, u, first, last), db, u)
        await asyncio.sleep(0.2)

    for u in users_due_for_reminder(db):
        if await _safe(bot.send_message(u["telegram_id"], t(u["language"], "reminder.text")), db, u):
            service.update_user(db, u["telegram_id"], last_reminder_date=service.user_today(u).isoformat())
        await asyncio.sleep(0.05)


async def scheduler_loop(bot: Bot, db: Database) -> None:
    log.info("scheduler started")
    while True:
        try:
            await run_once(bot, db)
        except Exception:
            log.exception("scheduler tick failed")
        await asyncio.sleep(TICK_SECONDS)
