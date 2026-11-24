"""SQLite storage. Plain sqlite3 is enough here: queries are tiny and the bot is I/O bound on Telegram."""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id        INTEGER PRIMARY KEY,
    name               TEXT,
    language           TEXT NOT NULL DEFAULT 'en',
    currency           TEXT NOT NULL DEFAULT 'UZS',
    timezone           TEXT NOT NULL DEFAULT 'Asia/Tashkent',
    split              TEXT NOT NULL DEFAULT '50,30,20',
    tips_enabled       INTEGER NOT NULL DEFAULT 1,
    tip_time           TEXT NOT NULL DEFAULT '09:00',
    reminders_enabled  INTEGER NOT NULL DEFAULT 0,
    guided_mode        INTEGER NOT NULL DEFAULT 1,
    onboarded          INTEGER NOT NULL DEFAULT 0,
    last_tip_date      TEXT,
    last_report_month  TEXT,
    last_reminder_date TEXT,
    created_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS profiles (
    user_id      INTEGER PRIMARY KEY REFERENCES users(telegram_id) ON DELETE CASCADE,
    age          INTEGER,
    occupation   TEXT,
    is_student   INTEGER,
    income       REAL,
    debt_total   REAL,
    debt_monthly REAL,
    goal         TEXT
);

CREATE TABLE IF NOT EXISTS categories (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    key     TEXT,           -- default categories: translation key; custom ones: NULL
    name    TEXT,           -- custom categories only
    emoji   TEXT NOT NULL,
    bucket  TEXT NOT NULL,
    UNIQUE (user_id, key)
);

CREATE TABLE IF NOT EXISTS expenses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    amount      REAL NOT NULL,
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    bucket      TEXT NOT NULL,
    note        TEXT NOT NULL DEFAULT '',
    spent_on    TEXT NOT NULL,           -- YYYY-MM-DD
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_expenses_user_date ON expenses (user_id, spent_on);
CREATE INDEX IF NOT EXISTS idx_expenses_user_cat  ON expenses (user_id, category_id, spent_on);

CREATE TABLE IF NOT EXISTS incomes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    amount      REAL NOT NULL,
    source      TEXT NOT NULL DEFAULT '',
    received_on TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_incomes_user_date ON incomes (user_id, received_on);

CREATE TABLE IF NOT EXISTS allocations (
    income_id INTEGER NOT NULL REFERENCES incomes(id) ON DELETE CASCADE,
    bucket    TEXT NOT NULL,
    percent   REAL NOT NULL,
    amount    REAL NOT NULL,
    PRIMARY KEY (income_id, bucket)
);

CREATE TABLE IF NOT EXISTS tips_sent (
    user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    tip_id  INTEGER NOT NULL,
    sent_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, tip_id)
);
"""


class Database:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        if str(path) != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")
        self._lock = threading.RLock()
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def execute(self, sql: str, params: tuple | list = ()) -> int:
        """Run a write statement and return lastrowid."""
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur.lastrowid

    def query(self, sql: str, params: tuple | list = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def one(self, sql: str, params: tuple | list = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def scalar(self, sql: str, params: tuple | list = (), default=None):
        row = self.one(sql, params)
        if row is None or row[0] is None:
            return default
        return row[0]

    def transaction(self):
        """Use as: with db.transaction() as conn: conn.execute(...). Commits on success."""
        return _Tx(self)

    def close(self) -> None:
        with self._lock:
            self._conn.close()


class _Tx:
    def __init__(self, db: Database):
        self.db = db

    def __enter__(self):
        self.db._lock.acquire()
        return self.db._conn

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self.db._conn.commit()
            else:
                self.db._conn.rollback()
        finally:
            self.db._lock.release()
        return False
