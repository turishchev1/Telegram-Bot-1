"""Business logic on top of the database. No Telegram code in here, so it can be tested on its own."""
from __future__ import annotations

from datetime import date

from . import config
from .categories import DEFAULT_CATEGORIES, guess_default_category, match_custom
from .db import Database
from .utils import now_in

USER_FIELDS = {
    "name", "language", "currency", "timezone", "split", "tips_enabled", "tip_time",
    "reminders_enabled", "guided_mode", "onboarded", "last_tip_date", "last_report_month",
    "last_reminder_date",
}
PROFILE_FIELDS = {"age", "occupation", "is_student", "income", "debt_total", "debt_monthly", "goal"}


# ---------------------------------------------------------------- users
def get_user(db: Database, tid: int):
    return db.one("SELECT * FROM users WHERE telegram_id = ?", (tid,))


def get_or_create_user(db: Database, tid: int, name: str | None = None, language: str | None = None):
    user = get_user(db, tid)
    if user:
        return user
    lang = language if language in config.LANGUAGES else config.DEFAULT_LANGUAGE
    db.execute(
        "INSERT INTO users (telegram_id, name, language, currency, timezone) VALUES (?,?,?,?,?)",
        (tid, name, lang, config.DEFAULT_CURRENCY, config.DEFAULT_TIMEZONE),
    )
    for key, emoji, bucket in DEFAULT_CATEGORIES:
        db.execute(
            "INSERT INTO categories (user_id, key, emoji, bucket) VALUES (?,?,?,?)",
            (tid, key, emoji, bucket),
        )
    return get_user(db, tid)


def update_user(db: Database, tid: int, **fields) -> None:
    bad = set(fields) - USER_FIELDS
    if bad:
        raise ValueError(f"unknown user fields: {bad}")
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    db.execute(f"UPDATE users SET {cols} WHERE telegram_id = ?", (*fields.values(), tid))


def get_split(user) -> tuple[int, int, int]:
    try:
        a, b, c = (int(float(x)) for x in str(user["split"]).split(","))
        return a, b, c
    except (ValueError, TypeError):
        return config.DEFAULT_SPLIT


def get_profile(db: Database, tid: int):
    return db.one("SELECT * FROM profiles WHERE user_id = ?", (tid,))


def save_profile(db: Database, tid: int, **fields) -> None:
    bad = set(fields) - PROFILE_FIELDS
    if bad:
        raise ValueError(f"unknown profile fields: {bad}")
    db.execute("INSERT OR IGNORE INTO profiles (user_id) VALUES (?)", (tid,))
    if fields:
        cols = ", ".join(f"{k} = ?" for k in fields)
        db.execute(f"UPDATE profiles SET {cols} WHERE user_id = ?", (*fields.values(), tid))


def delete_user_data(db: Database, tid: int) -> None:
    """Remove the user and everything attached to them (cascades)."""
    db.execute("DELETE FROM users WHERE telegram_id = ?", (tid,))


def user_today(user) -> date:
    return now_in(user["timezone"], config.DEFAULT_TIMEZONE).date()


# ----------------------------------------------------------- categories
def list_categories(db: Database, tid: int):
    return db.query("SELECT * FROM categories WHERE user_id = ? ORDER BY id", (tid,))


def get_category(db: Database, tid: int, cid: int):
    return db.one("SELECT * FROM categories WHERE id = ? AND user_id = ?", (cid, tid))


def category_by_key(db: Database, tid: int, key: str):
    return db.one("SELECT * FROM categories WHERE user_id = ? AND key = ?", (tid, key))


def add_category(db: Database, tid: int, name: str, emoji: str = "🏷", bucket: str = "wants") -> int:
    if bucket not in config.BUCKETS:
        bucket = "wants"
    return db.execute(
        "INSERT INTO categories (user_id, key, name, emoji, bucket) VALUES (?,NULL,?,?,?)",
        (tid, name.strip()[:40], emoji, bucket),
    )


def resolve_category(db: Database, tid: int, note: str):
    """Best category row for a note, or None. Custom categories are checked first."""
    if not note:
        return None
    rows = list_categories(db, tid)
    custom = [(r["id"], r["name"]) for r in rows if r["key"] is None and r["name"]]
    cid = match_custom(note, custom)
    if cid is not None:
        return next(r for r in rows if r["id"] == cid)
    key = guess_default_category(note)
    if key:
        return next((r for r in rows if r["key"] == key), None)
    return None


# ------------------------------------------------------------- expenses
def add_expense(db: Database, tid: int, amount: float, category_id: int | None,
                note: str, spent_on: date) -> int:
    bucket = "wants"
    if category_id is not None:
        cat = get_category(db, tid, category_id)
        if cat is None:
            category_id = None
        else:
            bucket = cat["bucket"]
    return db.execute(
        "INSERT INTO expenses (user_id, amount, category_id, bucket, note, spent_on) VALUES (?,?,?,?,?,?)",
        (tid, round(amount, 2), category_id, bucket, note.strip()[:200], spent_on.isoformat()),
    )


_EXPENSE_SELECT = """
    SELECT e.*, c.key AS cat_key, c.name AS cat_name, c.emoji AS cat_emoji
    FROM expenses e LEFT JOIN categories c ON c.id = e.category_id
"""


def get_expense(db: Database, tid: int, eid: int):
    return db.one(_EXPENSE_SELECT + " WHERE e.id = ? AND e.user_id = ?", (eid, tid))


def last_expense(db: Database, tid: int):
    return db.one(_EXPENSE_SELECT + " WHERE e.user_id = ? ORDER BY e.id DESC LIMIT 1", (tid,))


def delete_expense(db: Database, tid: int, eid: int) -> bool:
    if get_expense(db, tid, eid) is None:
        return False
    db.execute("DELETE FROM expenses WHERE id = ? AND user_id = ?", (eid, tid))
    return True


def set_expense_category(db: Database, tid: int, eid: int, cid: int) -> bool:
    cat = get_category(db, tid, cid)
    if cat is None or get_expense(db, tid, eid) is None:
        return False
    db.execute(
        "UPDATE expenses SET category_id = ?, bucket = ? WHERE id = ? AND user_id = ?",
        (cid, cat["bucket"], eid, tid),
    )
    return True


def query_expenses(db: Database, tid: int, *, category_id: int | None = None,
                   bucket: str | None = None, start: date | None = None, end: date | None = None,
                   min_amount: float | None = None, text: str | None = None,
                   limit: int | None = None, offset: int = 0, order: str = "date"):
    """Returns (rows, total, count). Newest first (or biggest first with order="amount").
    `total` and `count` cover all matches, not just the page."""
    where, params = ["e.user_id = ?"], [tid]
    if category_id is not None:
        where.append("e.category_id = ?")
        params.append(category_id)
    if bucket:
        where.append("e.bucket = ?")
        params.append(bucket)
    if start:
        where.append("e.spent_on >= ?")
        params.append(start.isoformat())
    if end:
        where.append("e.spent_on <= ?")
        params.append(end.isoformat())
    if min_amount is not None:
        where.append("e.amount >= ?")
        params.append(min_amount)
    if text:
        where.append("LOWER(e.note) LIKE ?")
        params.append(f"%{text.lower()}%")
    clause = " WHERE " + " AND ".join(where)
    agg = db.one(f"SELECT COALESCE(SUM(e.amount),0) AS total, COUNT(*) AS n FROM expenses e{clause}", params)
    order_sql = "e.amount DESC, e.id DESC" if order == "amount" else "e.spent_on DESC, e.id DESC"
    sql = _EXPENSE_SELECT + clause + " ORDER BY " + order_sql
    page_params = list(params)
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        page_params += [limit, offset]
    return db.query(sql, page_params), float(agg["total"]), int(agg["n"])


# --------------------------------------------------------------- income
def split_amounts(amount: float, percents: tuple | list) -> list[float]:
    """Cut `amount` by percentages that must add up to 100. The last share takes the rounding remainder."""
    if abs(sum(percents) - 100) > 0.01:
        raise ValueError("percentages must add up to 100")
    shares = [round(amount * p / 100, 2) for p in percents[:-1]]
    shares.append(round(amount - sum(shares), 2))
    return shares


def add_income(db: Database, tid: int, amount: float, source: str, received_on: date,
               percents: tuple | list) -> int:
    shares = split_amounts(amount, percents)
    with db.transaction() as conn:
        cur = conn.execute(
            "INSERT INTO incomes (user_id, amount, source, received_on) VALUES (?,?,?,?)",
            (tid, round(amount, 2), source.strip()[:100], received_on.isoformat()),
        )
        iid = cur.lastrowid
        for bucket, pct, share in zip(config.BUCKETS, percents, shares):
            conn.execute(
                "INSERT INTO allocations (income_id, bucket, percent, amount) VALUES (?,?,?,?)",
                (iid, bucket, pct, share),
            )
    return iid


def get_income(db: Database, tid: int, iid: int):
    return db.one("SELECT * FROM incomes WHERE id = ? AND user_id = ?", (iid, tid))


def last_income(db: Database, tid: int):
    return db.one("SELECT * FROM incomes WHERE user_id = ? ORDER BY id DESC LIMIT 1", (tid,))


def delete_income(db: Database, tid: int, iid: int) -> bool:
    if get_income(db, tid, iid) is None:
        return False
    db.execute("DELETE FROM incomes WHERE id = ? AND user_id = ?", (iid, tid))
    return True


def income_allocations(db: Database, iid: int):
    return db.query("SELECT * FROM allocations WHERE income_id = ?", (iid,))


def list_incomes(db: Database, tid: int, start: date | None = None, end: date | None = None):
    where, params = ["user_id = ?"], [tid]
    if start:
        where.append("received_on >= ?")
        params.append(start.isoformat())
    if end:
        where.append("received_on <= ?")
        params.append(end.isoformat())
    return db.query(
        "SELECT * FROM incomes WHERE " + " AND ".join(where) + " ORDER BY received_on, id", params
    )


# ------------------------------------------------------------- balances
def bucket_balances(db: Database, tid: int, month_start: date, month_end: date) -> dict:
    """Per bucket: money allocated from income, money spent (all time), what is left,
    and what was spent in the given month. Unspent money rolls over from month to month."""
    out = {b: {"allocated": 0.0, "spent": 0.0, "left": 0.0, "month_spent": 0.0} for b in config.BUCKETS}
    for r in db.query(
        "SELECT a.bucket, SUM(a.amount) AS s FROM allocations a JOIN incomes i ON i.id = a.income_id "
        "WHERE i.user_id = ? GROUP BY a.bucket", (tid,)):
        if r["bucket"] in out:
            out[r["bucket"]]["allocated"] = float(r["s"])
    for r in db.query(
        "SELECT bucket, SUM(amount) AS s FROM expenses WHERE user_id = ? GROUP BY bucket", (tid,)):
        if r["bucket"] in out:
            out[r["bucket"]]["spent"] = float(r["s"])
    for r in db.query(
        "SELECT bucket, SUM(amount) AS s FROM expenses WHERE user_id = ? AND spent_on BETWEEN ? AND ? "
        "GROUP BY bucket", (tid, month_start.isoformat(), month_end.isoformat())):
        if r["bucket"] in out:
            out[r["bucket"]]["month_spent"] = float(r["s"])
    for v in out.values():
        v["left"] = round(v["allocated"] - v["spent"], 2)
    return out
