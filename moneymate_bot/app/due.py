"""Which users are due for a daily tip, a monthly report or a logging reminder right now.
Pure database logic (no Telegram), so it can be tested without the bot."""
from __future__ import annotations

from datetime import datetime

from . import config
from .db import Database
from .utils import add_months, local_now, month_bounds, month_key


def users_due_for_tip(db: Database, now_utc: datetime | None = None) -> list:
    due = []
    for u in db.query("SELECT * FROM users WHERE onboarded = 1 AND tips_enabled = 1"):
        local = local_now(u["timezone"], config.DEFAULT_TIMEZONE, now_utc)
        if u["last_tip_date"] != local.date().isoformat() and local.strftime("%H:%M") >= u["tip_time"]:
            due.append(u)
    return due


def users_due_for_report(db: Database, now_utc: datetime | None = None) -> list[tuple]:
    """[(user, first_day_of_previous_month, last_day_of_previous_month)] for users whose
    monthly report has not been sent yet. Reports go out from 09:00 local time on the 1st, and are
    still sent during the first week if the bot was offline on the 1st."""
    due = []
    for u in db.query("SELECT * FROM users WHERE onboarded = 1"):
        local = local_now(u["timezone"], config.DEFAULT_TIMEZONE, now_utc)
        if local.day > 7 or (local.day == 1 and local.strftime("%H:%M") < "09:00"):
            continue  # only in the first week of the month, never before 09:00 on the 1st
        prev_first, prev_last = month_bounds(add_months(local.date(), -1))
        if u["last_report_month"] == month_key(prev_first):
            continue
        due.append((u, prev_first, prev_last))
    return due


def users_due_for_reminder(db: Database, now_utc: datetime | None = None) -> list:
    due = []
    for u in db.query("SELECT * FROM users WHERE onboarded = 1 AND reminders_enabled = 1"):
        local = local_now(u["timezone"], config.DEFAULT_TIMEZONE, now_utc)
        today = local.date().isoformat()
        if u["last_reminder_date"] == today or local.strftime("%H:%M") < "20:00":
            continue
        logged = db.scalar(
            "SELECT COUNT(*) FROM expenses WHERE user_id = ? AND spent_on = ?", (u["telegram_id"], today), 0)
        if not logged:
            due.append(u)
    return due
