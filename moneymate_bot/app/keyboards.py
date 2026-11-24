"""Inline keyboard helpers. Callback data stays short (Telegram allows 64 bytes)."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from . import config, service
from .i18n import category_name, t


def kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    """rows of (button text, callback data)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, callback_data=data) for text, data in row]
                         for row in rows]
    )


def language_kb(prefix: str) -> InlineKeyboardMarkup:
    flags = {"en": "🇬🇧", "ru": "🇷🇺", "uz": "🇺🇿"}
    return kb([[(f"{flags[c]} {name}", f"{prefix}:{c}") for c, name in config.LANGUAGES.items()]])


def skip_kb(lang: str, data: str = "ob_skip") -> InlineKeyboardMarkup:
    return kb([[(t(lang, "btn.skip"), data)]])


def categories_kb(db, tid: int, lang: str, prefix: str, columns: int = 2) -> InlineKeyboardMarkup:
    cats = service.list_categories(db, tid)
    buttons = [(f"{c['emoji']} {category_name(c, lang)}", f"{prefix}:{c['id']}") for c in cats]
    rows = [buttons[i:i + columns] for i in range(0, len(buttons), columns)]
    return kb(rows)


def date_kb(lang: str) -> InlineKeyboardMarkup:
    return kb([
        [(t(lang, "btn.today"), "date:today"), (t(lang, "btn.yesterday"), "date:yesterday")],
        [(t(lang, "btn.pick_date"), "date:pick")],
    ])
