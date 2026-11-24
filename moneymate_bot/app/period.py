"""Understand period words in commands such as `/show food last month` or `/show transport october`."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from . import config
from .categories import normalize, tokens
from .i18n import t
from .utils import add_months, month_bounds, week_start

TODAY = {"today", "сегодня", "bugun"}
WEEK = {"week", "неделя", "неделю", "неделе", "hafta", "haftalik"}
MONTH = {"month", "месяц", "месяца", "oy", "oylik"}
LAST = {"last", "previous", "прошлый", "прошлом", "прошлого", "прошлая", "otgan", "avvalgi", "oldingi"}
YEAR = {"year", "год", "году", "yil"}
ALL = {"all", "alltime", "всё", "все", "hammasi", "barchasi"}

_month_names: dict[str, int] | None = None


def _months() -> dict[str, int]:
    global _month_names
    if _month_names is None:
        _month_names = {}
        for lang in config.LANGUAGES:
            for m in range(1, 13):
                _month_names[normalize(t(lang, f"month.{m}"))] = m
    return _month_names


def _month_from_word(word: str) -> int | None:
    if len(word) < 3:
        return None
    for name, m in _months().items():
        if word == name or word[:3] == name[:3] and len(word) <= len(name) + 2:
            return m
    return None


@dataclass
class Period:
    start: date
    end: date
    kind: str  # today | week | month | last_month | year | all | month_name


def parse_period(words: list[str], today: date) -> tuple[Period | None, list[str]]:
    """Split words into a period (None if no period word was found) and the leftover words."""
    toks = [normalize(w) for w in words]
    leftover: list[str] = []
    kind: str | None = None
    last = False
    month_no: int | None = None
    year_no: int | None = None
    for raw, tok in zip(words, toks):
        if tok in TODAY:
            kind = "today"
        elif tok in WEEK:
            kind = "week"
        elif tok in MONTH:
            kind = "month"
        elif tok in LAST:
            last = True
        elif tok in YEAR:
            kind = "year"
        elif tok in ALL:
            kind = "all"
        elif tok.isdigit() and len(tok) == 4 and 2000 <= int(tok) <= 2100:
            year_no = int(tok)
        elif _month_from_word(tok):
            month_no = _month_from_word(tok)
        else:
            leftover.append(raw)

    if month_no is not None:
        year = year_no or today.year
        if year_no is None and date(year, month_no, 1) > today:
            year -= 1
        first = date(year, month_no, 1)
        return Period(first, month_bounds(first)[1], "month_name"), leftover
    if year_no is not None:
        return Period(date(year_no, 1, 1), date(year_no, 12, 31), "year"), leftover
    if kind == "month" and last:
        first = add_months(today, -1)
        return Period(first, month_bounds(first)[1], "last_month"), leftover
    if kind == "today":
        return Period(today, today, "today"), leftover
    if kind == "week":
        return Period(week_start(today), today, "week"), leftover
    if kind == "month":
        first, end = month_bounds(today)
        return Period(first, end, "month"), leftover
    if kind == "year":
        return Period(date(today.year, 1, 1), date(today.year, 12, 31), "year"), leftover
    if kind == "all":
        return Period(date(2000, 1, 1), date(2100, 12, 31), "all"), leftover
    if last:  # "last" alone: treat as last month
        first = add_months(today, -1)
        return Period(first, month_bounds(first)[1], "last_month"), leftover
    return None, leftover


def period_label(lang: str, start: date, end: date, today: date) -> str:
    """Human label for a date range: 'today', 'November 2026', '10.11.2026 – 16.11.2026'."""
    if start.year == 2000 and end.year == 2100:
        return t(lang, "period.all")
    if start == end:
        return t(lang, "period.today") if start == today else start.strftime("%d.%m.%Y")
    if start.day == 1 and end == month_bounds(start)[1]:
        return f"{t(lang, f'month.{start.month}')} {start.year}"
    if start == date(start.year, 1, 1) and end == date(start.year, 12, 31):
        return str(start.year)
    return f"{start.strftime('%d.%m.%Y')} – {end.strftime('%d.%m.%Y')}"
