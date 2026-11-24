"""Translations. Every user-facing string lives in app/locales/<lang>.json and is fetched with t()."""
from __future__ import annotations

import json
from pathlib import Path

from . import config

LOCALE_DIR = Path(__file__).parent / "locales"
_cache: dict[str, dict[str, str]] = {}


def _load(lang: str) -> dict[str, str]:
    if lang not in _cache:
        path = LOCALE_DIR / f"{lang}.json"
        _cache[lang] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return _cache[lang]


def t(lang: str, key: str, **kwargs) -> str:
    """Look up `key` in `lang`, falling back to English, then to the key itself.
    Placeholders use str.format syntax: t("en", "saved", amount="5 000")."""
    text = _load(lang).get(key) or _load("en").get(key) or key
    return text.format(**kwargs) if kwargs else text


def has_key(lang: str, key: str) -> bool:
    return key in _load(lang)


def month_name(lang: str, month: int) -> str:
    return t(lang, f"month.{month}")


def month_short(lang: str, month: int) -> str:
    return t(lang, f"month_short.{month}")


def weekday_short(lang: str, weekday: int) -> str:
    return t(lang, f"weekday_short.{weekday}")


def weekday_name(lang: str, weekday: int) -> str:
    """weekday: Monday = 0."""
    return t(lang, f"weekday.{weekday}")


def category_name(row, lang: str) -> str:
    """Name of a category row (default categories are translated, custom ones keep their own name)."""
    if row is None:
        return t(lang, "cat.other")
    if row["key"]:
        return t(lang, f"cat.{row['key']}")
    return row["name"] or t(lang, "cat.other")


def bucket_name(lang: str, bucket: str) -> str:
    return t(lang, f"bucket.{bucket}")


def detect_language(telegram_code: str | None) -> str:
    code = (telegram_code or "").lower()[:2]
    return code if code in config.LANGUAGES else config.DEFAULT_LANGUAGE
