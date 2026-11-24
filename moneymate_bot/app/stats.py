"""Spending statistics and the habit insights shown by /stats."""
from __future__ import annotations

from datetime import date, timedelta

from . import config
from .db import Database
from .i18n import bucket_name, category_name, month_name, t, weekday_name
from .utils import add_months, format_money, month_bounds, month_key


def monthly_totals(db: Database, tid: int, months: int, today: date) -> list[tuple[date, float]]:
    """Totals for the last `months` calendar months (oldest first), zero-filled."""
    first = add_months(today, -(months - 1))
    rows = db.query(
        "SELECT substr(spent_on,1,7) AS ym, SUM(amount) AS s FROM expenses "
        "WHERE user_id = ? AND spent_on >= ? GROUP BY ym", (tid, first.isoformat()))
    by_ym = {r["ym"]: float(r["s"]) for r in rows}
    out = []
    for i in range(months):
        m = add_months(first, i)
        out.append((m, by_ym.get(month_key(m), 0.0)))
    return out


def all_months(db: Database, tid: int) -> dict[str, float]:
    rows = db.query(
        "SELECT substr(spent_on,1,7) AS ym, SUM(amount) AS s FROM expenses WHERE user_id = ? GROUP BY ym",
        (tid,))
    return {r["ym"]: float(r["s"]) for r in rows}


def weekday_totals(db: Database, tid: int, start: date, end: date) -> list[tuple[float, int]]:
    """[(total, count)] for Monday..Sunday."""
    out = [(0.0, 0)] * 7
    rows = db.query(
        "SELECT CAST(strftime('%w', spent_on) AS INTEGER) AS w, SUM(amount) AS s, COUNT(*) AS n "
        "FROM expenses WHERE user_id = ? AND spent_on BETWEEN ? AND ? GROUP BY w",
        (tid, start.isoformat(), end.isoformat()))
    for r in rows:
        out[(r["w"] + 6) % 7] = (float(r["s"]), int(r["n"]))
    return out


def category_totals(db: Database, tid: int, start: date, end: date) -> list[dict]:
    """Per category spending in the period, biggest first. Uncategorised spending is reported as 'other'."""
    rows = db.query(
        "SELECT c.id AS id, c.key AS key, c.name AS name, c.emoji AS emoji, c.bucket AS bucket, "
        "SUM(e.amount) AS total, COUNT(*) AS n "
        "FROM expenses e LEFT JOIN categories c ON c.id = e.category_id "
        "WHERE e.user_id = ? AND e.spent_on BETWEEN ? AND ? "
        "GROUP BY e.category_id ORDER BY total DESC", (tid, start.isoformat(), end.isoformat()))
    return [dict(r) for r in rows]


def bucket_totals(db: Database, tid: int, start: date, end: date) -> dict[str, float]:
    out = {b: 0.0 for b in config.BUCKETS}
    for r in db.query(
        "SELECT bucket, SUM(amount) AS s FROM expenses WHERE user_id = ? AND spent_on BETWEEN ? AND ? "
        "GROUP BY bucket", (tid, start.isoformat(), end.isoformat())):
        if r["bucket"] in out:
            out[r["bucket"]] = float(r["s"])
    return out


def period_total(db: Database, tid: int, start: date, end: date) -> float:
    return float(db.scalar(
        "SELECT SUM(amount) FROM expenses WHERE user_id = ? AND spent_on BETWEEN ? AND ?",
        (tid, start.isoformat(), end.isoformat()), default=0.0))


def days_with_expenses(db: Database, tid: int, start: date, end: date) -> int:
    return int(db.scalar(
        "SELECT COUNT(DISTINCT spent_on) FROM expenses WHERE user_id = ? AND spent_on BETWEEN ? AND ?",
        (tid, start.isoformat(), end.isoformat()), default=0))


def insight_lines(db: Database, user, today: date) -> list[str]:
    """Human-readable habit insights in the user's language. Empty list when there is no data yet."""
    tid, lang, cur = user["telegram_id"], user["language"], user["currency"]
    money = lambda x: format_money(x, cur)  # noqa: E731
    lines: list[str] = []

    m_start, m_end = month_bounds(today)
    p_start, p_end = month_bounds(add_months(today, -1))
    this_total = period_total(db, tid, m_start, m_end)
    prev_total = period_total(db, tid, p_start, p_end)

    if this_total > 0 and prev_total > 0:
        change = (this_total - prev_total) / prev_total * 100
        key = "insight.vs_prev_up" if change >= 0 else "insight.vs_prev_down"
        lines.append(t(lang, key, pct=f"{abs(change):.0f}", total=money(this_total),
                       prev=month_name(lang, p_start.month)))
    elif this_total > 0:
        lines.append(t(lang, "insight.month_total", total=money(this_total)))

    months = all_months(db, tid)
    if len(months) >= 2:
        top_ym = max(months, key=months.get)
        low_ym = min(months, key=months.get)
        lines.append(t(lang, "insight.top_month", month=month_name(lang, int(top_ym[5:7])),
                       year=top_ym[:4], total=money(months[top_ym])))
        if low_ym != top_ym:
            lines.append(t(lang, "insight.low_month", month=month_name(lang, int(low_ym[5:7])),
                           year=low_ym[:4], total=money(months[low_ym])))

    wd = weekday_totals(db, tid, today - timedelta(days=90), today)
    if sum(n for _, n in wd) >= 7 and max(s for s, _ in wd) > 0:
        best = max(range(7), key=lambda i: wd[i][0])
        lines.append(t(lang, "insight.top_weekday", weekday=weekday_name(lang, best), total=money(wd[best][0])))

    cats = category_totals(db, tid, m_start, m_end)
    if cats and this_total > 0:
        top = cats[0]
        lines.append(t(lang, "insight.top_category", emoji=top["emoji"] or "➕",
                       category=category_name(top if top["id"] else None, lang),
                       total=money(top["total"]), pct=f"{top['total'] / this_total * 100:.0f}"))
        frequent = max(cats, key=lambda c: c["n"])
        if frequent["n"] >= 5:
            lines.append(t(lang, "insight.frequent", n=frequent["n"], emoji=frequent["emoji"] or "➕",
                           category=category_name(frequent if frequent["id"] else None, lang),
                           total=money(frequent["total"])))

    prev_cats = {c["id"]: c["total"] for c in category_totals(db, tid, p_start, p_end)}
    best_jump = None
    for c in cats:
        before = prev_cats.get(c["id"], 0)
        if before > 0 and c["total"] > before * 1.2:
            jump = (c["total"] - before) / before
            if best_jump is None or jump > best_jump[0]:
                best_jump = (jump, c)
    if best_jump:
        c = best_jump[1]
        lines.append(t(lang, "insight.category_up", emoji=c["emoji"] or "➕",
                       category=category_name(c if c["id"] else None, lang),
                       pct=f"{best_jump[0] * 100:.0f}"))

    if this_total > 0:
        elapsed = (today - m_start).days + 1
        no_spend = elapsed - days_with_expenses(db, tid, m_start, today)
        if no_spend > 0 and elapsed >= 7:
            lines.append(t(lang, "insight.no_spend", n=no_spend, days=elapsed))
        bt = bucket_totals(db, tid, m_start, m_end)
        parts = [f"{bucket_name(lang, b)} {bt[b] / this_total * 100:.0f}%" for b in config.BUCKETS]
        lines.append(t(lang, "insight.bucket_mix", mix=" · ".join(parts)))
    return lines
