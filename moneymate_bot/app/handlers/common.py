"""Shared pieces for all handlers: middleware, FSM states and small helpers."""
from __future__ import annotations

import html
import logging
from datetime import date

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from .. import context, service
from ..i18n import detect_language, t
from ..utils import format_money

log = logging.getLogger(__name__)



def esc(text) -> str:
    """Escape user text for Telegram's HTML parse mode. Only & < > need escaping; leaving quotes
    and apostrophes alone keeps Uzbek text (o', g') readable and avoids numeric entities."""
    return html.escape(str(text), quote=False)


class UserMiddleware(BaseMiddleware):
    """Makes sure every sender has a row in the database and hands `db`, `user` and `lang` to handlers."""

    async def __call__(self, handler, event, data):
        tg = data.get("event_from_user")
        db = context.get_db()
        data["db"] = db
        if tg is not None and not tg.is_bot:
            user = service.get_or_create_user(db, tg.id, tg.full_name, detect_language(tg.language_code))
            data["user"] = user
            data["lang"] = user["language"]
        return await handler(event, data)


class Onboarding(StatesGroup):
    name = State()
    age = State()
    job = State()
    income = State()
    debt = State()
    debt_total = State()
    debt_monthly = State()
    goal = State()


class AddExpense(StatesGroup):
    category = State()
    date = State()
    date_text = State()
    note = State()


class IncomeFlow(StatesGroup):
    amount = State()
    choose = State()
    custom = State()


class SettingsFlow(StatesGroup):
    timezone = State()
    tip_time = State()
    new_category = State()
    search = State()


async def safe_edit(message: Message, text: str, reply_markup=None) -> None:
    """Edit a bot message, ignoring Telegram's 'message is not modified' error."""
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "not modified" not in str(exc).lower():
            log.warning("edit_text failed: %s", exc)


def money(user, amount: float) -> str:
    return format_money(amount, user["currency"])


def fmt_date(d: date | str) -> str:
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return d.strftime("%d.%m")


def need_start_text(lang: str) -> str:
    return t(lang, "need_start")
