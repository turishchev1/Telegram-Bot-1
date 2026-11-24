"""Small helpers: money formatting, month maths, validation."""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ZERO_DECIMAL_CURRENCIES = {"UZS", "RUB"}


def format_money(amount: float, currency: str = "UZS") -> str:
    """15000 UZS -> '15 000 UZS', 1234.5 USD -> '$1,234.50'."""
    neg = amount < 0
    a = abs(amount)
    if currency in ZERO_DECIMAL_CURRENCIES:
        body = f"{round(a):,}".replace(",", " ")
    else:
        body = f"{a:,.2f}"
        if body.endswith(".00") and a >= 1000:
            body = body[:-3]
    sign = "-" if neg else ""
    if currency == "UZS":
        return f"{sign}{body} UZS"
    if currency == "RUB":
        return f"{sign}{body} ₽"
    if currency == "USD":
        return f"{sign}${body}"
    if currency == "EUR":
        return f"{sign}€{body}"
    return f"{sign}{body} {currency}"


def month_bounds(d: date) -> tuple[date, date]:
    first = d.replace(day=1)
    last = d.replace(day=calendar.monthrange(d.year, d.month)[1])
    return first, last


def add_months(d: date, n: int) -> date:
    """First day of the month n months away from d's month."""
    idx = d.year * 12 + (d.month - 1) + n
    return date(idx // 12, idx % 12 + 1, 1)


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def valid_timezone(name: str) -> bool:
    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return False


def local_now(tz_name: str, fallback: str = "Asia/Tashkent", now_utc: datetime | None = None) -> datetime:
    """Current time in the user's timezone (now_utc can be passed in for tests)."""
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        tz = ZoneInfo(fallback)
    return (now_utc or datetime.now(timezone.utc)).astimezone(tz)


def now_in(tz_name: str, fallback: str = "Asia/Tashkent") -> datetime:
    return local_now(tz_name, fallback)


_TIME_RE = re.compile(r"^\s*([01]?\d|2[0-3])(?:[:.]?([0-5]\d))?\s*$")


def parse_hhmm(text: str) -> str | None:
    """'9' -> '09:00', '21:30' -> '21:30', '2130' -> '21:30'; None if invalid."""
    m = _TIME_RE.match(text)
    if not m:
        return None
    return f"{int(m.group(1)):02d}:{m.group(2) or '00'}"


def parse_percent_list(text: str) -> list[float] | None:
    """'80 10 10' or '80/10/10' or '80,10,10' -> [80.0, 10.0, 10.0]."""
    parts = [p for p in re.split(r"[\s/,;:+]+", text.strip().replace("%", "")) if p]
    try:
        return [float(p) for p in parts]
    except ValueError:
        return None


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())
