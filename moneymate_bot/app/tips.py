"""Daily tips: pick one the user has not seen yet, leaning on their situation when it is known."""
from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

from . import service
from .db import Database
from .utils import month_bounds

TIPS_FILE = Path(__file__).parent / "data" / "tips.json"
_tips: list[dict] | None = None


def load_tips() -> list[dict]:
    global _tips
    if _tips is None:
        _tips = json.loads(TIPS_FILE.read_text(encoding="utf-8"))
    return _tips


def tip_text(tip: dict, lang: str) -> str:
    return tip.get(lang) or tip["en"]


def contextual_tags(db: Database, user, today: date) -> set[str]:
    """Tips tags that fit this user right now (debt, student, no recent logging, empty Wants...)."""
    tid = user["telegram_id"]
    tags: set[str] = set()
    profile = service.get_profile(db, tid)
    if profile:
        if (profile["debt_total"] or 0) > 0:
            tags.add("debt")
        if profile["is_student"]:
            tags.add("student")
        if profile["goal"] == "debt":
            tags.add("debt")
        elif profile["goal"] == "save":
            tags.add("saving")
        elif profile["goal"] == "emergency":
            tags.add("saving")
        elif profile["goal"] == "track":
            tags.add("habits")

    last = db.scalar("SELECT MAX(spent_on) FROM expenses WHERE user_id = ?", (tid,))
    if last is None or date.fromisoformat(last) < today - timedelta(days=3):
        tags.add("habits")

    first, last_day = month_bounds(today)
    bal = service.bucket_balances(db, tid, first, last_day)["wants"]
    if bal["allocated"] > 0 and bal["left"] <= bal["allocated"] * 0.1:
        tags.add("spending")
    return tags


def pick_tip(db: Database, user, today: date, rng: random.Random | None = None) -> dict | None:
    rng = rng or random.Random()
    tips = load_tips()
    if not tips:
        return None
    tid = user["telegram_id"]
    sent = {r["tip_id"] for r in db.query("SELECT tip_id FROM tips_sent WHERE user_id = ?", (tid,))}
    if len(sent) >= len(tips):  # seen them all: start over
        db.execute("DELETE FROM tips_sent WHERE user_id = ?", (tid,))
        sent = set()
    pool = [x for x in tips if x["id"] not in sent]
    wanted = contextual_tags(db, user, today)
    matching = [x for x in pool if x["tag"] in wanted]
    if matching and rng.random() < 0.6:
        return rng.choice(matching)
    return rng.choice(pool)


def mark_sent(db: Database, tid: int, tip_id: int) -> None:
    db.execute("INSERT OR REPLACE INTO tips_sent (user_id, tip_id) VALUES (?, ?)", (tid, tip_id))
