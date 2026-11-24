"""Turn a free-text message such as "taxi 22k yesterday" into amount, date and note.

Understands English, Russian and Uzbek (Latin) words for dates and number suffixes.
If a message holds several numbers, the largest one is taken as the amount
("3 coffees 45000" -> 45000) and the rest stays in the note.
Write dates as dd.mm or dd.mm.yyyy (month with two digits) so they are not mistaken for amounts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

from .categories import is_income_word, tokens

_DAY_BEFORE_RE = re.compile(r"(?<!\w)(?:day before yesterday|позавчера)(?!\w)", re.I)
_YESTERDAY_RE = re.compile(r"(?<!\w)(?:yesterday|вчера|kecha)(?!\w)", re.I)
_TODAY_RE = re.compile(r"(?<!\w)(?:today|сегодня|bugun)(?!\w)", re.I)
_ISO_RE = re.compile(r"(?<![\d.])(\d{4})-(\d{2})-(\d{2})(?![\d])")
_DMY_RE = re.compile(r"(?<![\d.,])(\d{1,2})[./](\d{2})(?:[./](\d{4}|\d{2}))?(?![\d.,/])")

_AMOUNT_RE = re.compile(
    r"""
    (?<![\w.,])
    (?P<num>\d{1,3}(?:[  ,.]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d+)?)
    (?:\s?(?P<suf>mln|million|ming|тысяч|тыс\.?|млн|k|к|m|м)(?!\w))?
    """,
    re.I | re.X,
)
_GROUPED_RE = re.compile(r"(\d{1,3}(?:[  ,.]\d{3})+)(?:[.,](\d{1,2}))?")
_PLAIN_RE = re.compile(r"(\d+)(?:[.,](\d+))?")

_THOUSAND = {"k", "к", "ming", "тыс", "тыс.", "тысяч"}
_MILLION = {"m", "м", "mln", "млн", "million"}

_CURRENCY_RE = re.compile(
    r"(?<!\w)(?:uzs|usd|rub|eur|so'?m|som|sum|сум|сўм|руб|рублей|dollar|dollars|доллар|долларов)(?!\w)|[$€₽]",
    re.I,
)


@dataclass
class Parsed:
    amount: float | None
    is_income: bool
    note: str
    date: date | None  # None when the message gave no date


def parse_number(raw: str, suffix: str | None = None) -> float | None:
    raw = raw.strip()
    m = _GROUPED_RE.fullmatch(raw)
    value: float
    if m and not m.group(1).lstrip().startswith("0"):
        whole = re.sub(r"[  ,.]", "", m.group(1))
        frac = m.group(2)
        value = float(whole + ("." + frac if frac else ""))
    else:
        m = _PLAIN_RE.fullmatch(raw)
        if not m:
            return None
        value = float(m.group(1) + ("." + m.group(2) if m.group(2) else ""))
    if suffix:
        s = suffix.lower()
        if s in _THOUSAND:
            value *= 1_000
        elif s in _MILLION:
            value *= 1_000_000
    return value


def _extract_date(text: str, today: date) -> tuple[str, date | None]:
    found: date | None = None

    def cut(pattern: re.Pattern, s: str) -> tuple[str, bool]:
        new, n = pattern.subn(" ", s, count=1)
        return new, n > 0

    text, hit = cut(_DAY_BEFORE_RE, text)
    if hit:
        return text, today - timedelta(days=2)
    text, hit = cut(_YESTERDAY_RE, text)
    if hit:
        return text, today - timedelta(days=1)
    text, hit = cut(_TODAY_RE, text)
    if hit:
        return text, today

    m = _ISO_RE.search(text)
    if m:
        try:
            found = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            found = None
        if found:
            return text[: m.start()] + " " + text[m.end():], found

    m = _DMY_RE.search(text)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year_raw = m.group(3)
        try:
            if year_raw:
                year = int(year_raw)
                if year < 100:
                    year += 2000
                found = date(year, month, day)
            else:
                found = date(today.year, month, day)
                if found > today:
                    found = date(today.year - 1, month, day)
        except ValueError:
            found = None
        if found:
            return text[: m.start()] + " " + text[m.end():], found
    return text, None


def parse_message(text: str, today: date) -> Parsed:
    s = text.strip()
    is_income = False
    if s.startswith("+"):
        is_income = True
        s = s[1:]
    elif s.startswith(("-", "−", "–")):
        s = s[1:]

    s, when = _extract_date(s, today)

    best = None  # (value, match)
    for m in _AMOUNT_RE.finditer(s):
        value = parse_number(m.group("num"), m.group("suf"))
        if value is None or value <= 0:
            continue
        if best is None or value >= best[0]:
            best = (value, m)

    if best is None:
        note = _clean_note(s)
        return Parsed(None, is_income, note, when)

    value, m = best
    rest = s[: m.start()] + " " + s[m.end():]
    note = _clean_note(rest)
    if not is_income and any(is_income_word(t) for t in tokens(note)):
        is_income = True
    return Parsed(round(value, 2), is_income, note, when)


def _clean_note(s: str) -> str:
    s = _CURRENCY_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip(" \t\n,.;:-–—+")
