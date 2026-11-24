"""Holds the one shared Database so handlers and the scheduler can reach it."""
from __future__ import annotations

from .db import Database

_db: Database | None = None


def set_db(db: Database) -> None:
    global _db
    _db = db


def get_db() -> Database:
    if _db is None:
        raise RuntimeError("Database not initialised: call context.set_db() first")
    return _db
