"""Looking at your data: summaries, /show, /search, /top, /balance, /stats, charts and Excel export."""
from __future__ import annotations

import logging
from datetime import date

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from .. import charts, config, exports, service, stats
from ..categories import normalize, tokens
from ..i18n import bucket_name, category_name, t
from ..keyboards import kb
from ..period import parse_period, period_label
from ..utils import add_months, month_bounds, month_key, week_start
from .common import SettingsFlow, esc, fmt_date, money, safe_edit

log = logging.getLogger(__name__)
router = Router(name="reports")
router.message.filter(F.chat.type == "private")

OVER_WORDS = {"over", "above", "больше", "ortiq", "dan"}


# ------------------------------------------------------------------ small formatters
def bar(used: float, total: float, width: int = 10) -> str:
    if total <= 0:
        return "░" * width
    filled = max(0, min(width, round(used / total * width)))
    return "█" * filled + "░" * (width - filled)


def entry_line(user, lang: str, e) -> str:
    cat = {"key": e["cat_key"], "name": e["cat_name"]} if e["category_id"] else None
    note = f" · {esc(e['note'])}" if e["note"] else ""
    return f"{fmt_date(e['spent_on'])} · {e['cat_emoji'] or '➕'} {esc(category_name(cat, lang))} · " \
           f"<b>{money(user, e['amount'])}</b>{note}"


def summary_text(db, user, start: date, end: date, today: date) -> str:
    """Total + per-category breakdown for any period."""
    lang, tid = user["language"], user["telegram_id"]
    total = stats.period_total(db, tid, start, end)
    label = period_label(lang, start, end, today)
    if total <= 0:
        return t(lang, "sum.empty", period=label)
    cats = stats.category_totals(db, tid, start, end)
    lines = [t(lang, "sum.title", period=label), t(lang, "sum.total", total=money(user, total)), ""]
    for c in cats[:8]:
        name = category_name(c if c["id"] else None, lang)
        lines.append(f"{c['emoji'] or '➕'} {esc(name)}: <b>{money(user, c['total'])}</b> "
                     f"({c['total'] / total * 100:.0f}%)")
    if len(cats) > 8:
        rest = sum(c["total"] for c in cats[8:])
        lines.append(t(lang, "sum.rest", total=money(user, rest)))
    n = int(db.scalar("SELECT COUNT(*) FROM expenses WHERE user_id = ? AND spent_on BETWEEN ? AND ?",
                      (tid, start.isoformat(), end.isoformat()), 0))
    lines += ["", t(lang, "sum.count", n=n)]
    return "\n".join(lines)


def balance_text(db, user, today: date) -> str:
    lang, tid = user["language"], user["telegram_id"]
    first, last = month_bounds(today)
    bal = service.bucket_balances(db, tid, first, last)
    if not any(v["allocated"] for v in bal.values()):
        return t(lang, "bal.empty")
    lines = [t(lang, "bal.title")]
    for b in config.BUCKETS:
        v = bal[b]
        pct = (v["spent"] / v["allocated"] * 100) if v["allocated"] > 0 else 0
        flag = " ⚠️" if v["left"] < 0 else (" 🟡" if v["allocated"] and v["left"] <= v["allocated"] * 0.2 else "")
        lines.append(f"\n<b>{bucket_name(lang, b)}</b>{flag}")
        lines.append(f"{bar(v['spent'], v['allocated'])} {pct:.0f}%")
        lines.append(t(lang, "bal.line", left=money(user, v["left"]), total=money(user, v["allocated"])))
    return "\n".join(lines)


# --------------------------------------------------------------------- quick summaries
@router.message(Command("today"))
async def cmd_today(message: Message, db, user) -> None:
    today = service.user_today(user)
    await message.answer(summary_text(db, user, today, today, today))


@router.message(Command("week"))
async def cmd_week(message: Message, db, user) -> None:
    today = service.user_today(user)
    await message.answer(summary_text(db, user, week_start(today), today, today))


@router.message(Command("month"))
async def cmd_month(message: Message, db, user) -> None:
    today = service.user_today(user)
    first, last = month_bounds(today)
    await message.answer(summary_text(db, user, first, last, today))


@router.message(Command("balance"))
async def cmd_balance(message: Message, db, user) -> None:
    await message.answer(balance_text(db, user, service.user_today(user)))


# ------------------------------------------------------------------------ /categories
def _category_menu(db, user, lang: str, today: date):
    first, last = month_bounds(today)
    totals = {c["id"]: c["total"] for c in stats.category_totals(db, user["telegram_id"], first, last)}
    rows, row = [], []
    for c in service.list_categories(db, user["telegram_id"]):
        total = totals.get(c["id"], 0)
        label = f"{c['emoji']} {category_name(c, lang)}" + (f" · {charts.compact(total)}" if total else "")
        row.append((label, f"shn:{c['id']}:-:{first:%Y%m%d}:{last:%Y%m%d}:0:0"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return kb(rows)


@router.message(Command("categories"))
async def cmd_categories(message: Message, db, user, lang: str) -> None:
    await message.answer(t(lang, "cat.menu_title"), reply_markup=_category_menu(db, user, lang, service.user_today(user)))


# ------------------------------------------------------------------------- /show
def _name_index() -> dict[str, str]:
    """Every translated default category name (all languages) -> category key."""
    idx: dict[str, str] = {}
    for lang in config.LANGUAGES:
        from ..categories import DEFAULT_CATEGORIES
        for key, _e, _b in DEFAULT_CATEGORIES:
            idx[normalize(t(lang, f"cat.{key}"))] = key
    return idx


def _bucket_index() -> dict[str, str]:
    idx: dict[str, str] = {}
    for lang in config.LANGUAGES:
        for b in config.BUCKETS:
            idx[normalize(t(lang, f"bucket.{b}"))] = b
    return idx


def resolve_filter(db, user, words: list[str]):
    """From leftover words work out (category_row, bucket, unresolved_text)."""
    if not words:
        return None, None, ""
    text = " ".join(words)
    buckets = _bucket_index()
    for w in words:
        if normalize(w) in buckets:
            return None, buckets[normalize(w)], ""
    names = _name_index()
    for w in words:
        key = names.get(normalize(w))
        if key:
            return service.category_by_key(db, user["telegram_id"], key), None, ""
    cat = service.resolve_category(db, user["telegram_id"], text)
    if cat is not None:
        return cat, None, ""
    return None, None, text


def _extract_min(words: list[str]) -> tuple[float | None, list[str]]:
    """Pull '>50000', 'over 50k' (also 'больше 50к', 'ortiq 50ming') out of the words."""
    from ..parser import parse_message
    out: list[str] = []
    minimum: float | None = None
    i = 0
    while i < len(words):
        w = words[i]
        if w.startswith(">") and len(w) > 1:
            amount = parse_message(w[1:], date.today()).amount
            if amount:
                minimum = amount
                i += 1
                continue
        if normalize(w) in OVER_WORDS and i + 1 < len(words):
            amount = parse_message(words[i + 1], date.today()).amount
            if amount:
                minimum = amount
                i += 2
                continue
        out.append(w)
        i += 1
    return minimum, out


async def render_list(db, user, *, cid: int, bucket: str | None, start: date, end: date,
                      minimum: float, page: int):
    lang, tid = user["language"], user["telegram_id"]
    today = service.user_today(user)
    per = config.PAGE_SIZE
    rows, total, n = service.query_expenses(
        db, tid, category_id=cid or None, bucket=bucket, start=start, end=end,
        min_amount=minimum or None, limit=per, offset=page * per)
    cat = service.get_category(db, tid, cid) if cid else None
    title = (f"{cat['emoji']} {esc(category_name(cat, lang))}" if cat
             else (bucket_name(lang, bucket) if bucket else t(lang, "show.all")))
    if n == 0:
        return t(lang, "show.empty", title=title, period=period_label(lang, start, end, today)), None
    lines = [f"<b>{title}</b> · {period_label(lang, start, end, today)}"]
    if minimum:
        lines.append(t(lang, "show.min", amount=money(user, minimum)))
    lines.append(t(lang, "show.summary", n=n, total=money(user, total), avg=money(user, total / n)))
    lines.append("")
    for i, e in enumerate(rows, start=1):
        lines.append(f"{i}. {entry_line(user, lang, e)}")
    pages = (n + per - 1) // per
    if pages > 1:
        lines.append("\n" + t(lang, "show.page", page=page + 1, pages=pages))

    base = f"{cid}:{bucket[0] if bucket else '-'}:{start:%Y%m%d}:{end:%Y%m%d}:{int(minimum or 0)}"
    pick = [(str(i), f"ex:{e['id']}") for i, e in enumerate(rows, start=1)]
    keyboard = [pick[:5], pick[5:]] if len(pick) > 5 else [pick]
    nav = []
    if page > 0:
        nav.append(("◀️", f"sh:{base}:{page - 1}"))
    if page + 1 < pages:
        nav.append(("▶️", f"sh:{base}:{page + 1}"))
    if nav:
        keyboard.append(nav)
    keyboard.append([(t(lang, "btn.export_csv"), f"csv:{base}")])
    return "\n".join(lines), kb(keyboard)


@router.message(Command("show"))
async def cmd_show(message: Message, command: CommandObject, db, user, lang: str) -> None:
    today = service.user_today(user)
    words = (command.args or "").split()
    if not words:
        await message.answer(t(lang, "show.help"), reply_markup=_category_menu(db, user, lang, today))
        return
    minimum, words = _extract_min(words)
    period, words = parse_period(words, today)
    cat, bucket, unresolved = resolve_filter(db, user, words)
    if unresolved:
        await message.answer(t(lang, "show.unknown", text=esc(unresolved)),
                             reply_markup=_category_menu(db, user, lang, today))
        return
    if period is None:
        start, end = month_bounds(today)
    else:
        start, end = period.start, period.end
    text, markup = await render_list(db, user, cid=cat["id"] if cat else 0, bucket=bucket,
                                     start=start, end=end, minimum=minimum or 0, page=0)
    await message.answer(text, reply_markup=markup)


def _parse_base(parts: list[str]):
    cid, b, s, e, minimum = parts[:5]
    bucket = {"n": "needs", "w": "wants", "s": "savings"}.get(b)
    start = date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    end = date(int(e[:4]), int(e[4:6]), int(e[6:8]))
    return int(cid), bucket, start, end, float(minimum)


@router.callback_query(F.data.startswith("sh:"))
@router.callback_query(F.data.startswith("shn:"))
async def on_show_page(cb: CallbackQuery, db, user) -> None:
    """sh: = turn the page of the list in place. shn: = open a list from a menu as a new message."""
    parts = cb.data.split(":")
    try:
        cid, bucket, start, end, minimum = _parse_base(parts[1:6])
        page = int(parts[6])
    except (ValueError, IndexError):
        await cb.answer()
        return
    text, markup = await render_list(db, user, cid=cid, bucket=bucket, start=start, end=end,
                                     minimum=minimum, page=page)
    await cb.answer()
    if parts[0] == "shn":
        await cb.message.answer(text, reply_markup=markup)
    else:
        await safe_edit(cb.message, text, markup)


@router.callback_query(F.data.startswith("ex:"))
async def on_entry(cb: CallbackQuery, db, user, lang: str) -> None:
    eid = int(cb.data.split(":", 1)[1])
    e = service.get_expense(db, user["telegram_id"], eid)
    await cb.answer()
    if e is None:
        return
    await cb.message.answer(
        entry_line(user, lang, e),
        reply_markup=kb([[(t(lang, "btn.change_category"), f"exp_cat:{eid}"),
                          (t(lang, "btn.delete"), f"exp_del:{eid}")]]))


@router.callback_query(F.data.startswith("csv:"))
async def on_csv(cb: CallbackQuery, db, user, lang: str) -> None:
    import csv
    import io
    try:
        cid, bucket, start, end, minimum = _parse_base(cb.data.split(":")[1:6])
    except (ValueError, IndexError):
        await cb.answer()
        return
    rows, _, _ = service.query_expenses(db, user["telegram_id"], category_id=cid or None, bucket=bucket,
                                        start=start, end=end, min_amount=minimum or None)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "category", "bucket", "amount", "note"])
    for e in reversed(list(rows)):
        cat = {"key": e["cat_key"], "name": e["cat_name"]} if e["category_id"] else None
        w.writerow([e["spent_on"], category_name(cat, lang), e["bucket"], e["amount"], e["note"]])
    await cb.answer()
    await cb.message.answer_document(
        BufferedInputFile(("﻿" + buf.getvalue()).encode("utf-8"), filename=f"expenses_{start:%Y%m%d}_{end:%Y%m%d}.csv"))


# ---------------------------------------------------------------- /search and /top
@router.message(Command("search"))
async def cmd_search(message: Message, command: CommandObject, db, user, lang: str) -> None:
    q = (command.args or "").strip()
    if not q:
        await message.answer(t(lang, "search.help"))
        return
    rows, total, n = service.query_expenses(db, user["telegram_id"], text=q, limit=30)
    if n == 0:
        await message.answer(t(lang, "search.none", q=esc(q)))
        return
    lines = [t(lang, "search.title", q=esc(q), n=n, total=money(user, total)), ""]
    lines += [entry_line(user, lang, e) for e in rows]
    await message.answer("\n".join(lines))


@router.message(Command("top"))
async def cmd_top(message: Message, command: CommandObject, db, user, lang: str) -> None:
    today = service.user_today(user)
    words = (command.args or "").split()
    period, words = parse_period(words, today)
    start, end = (period.start, period.end) if period else month_bounds(today)
    if words and normalize(words[0]).startswith(("cat", "кат", "toif")):
        cats = stats.category_totals(db, user["telegram_id"], start, end)
        if not cats:
            await message.answer(t(lang, "sum.empty", period=period_label(lang, start, end, today)))
            return
        total = sum(c["total"] for c in cats)
        lines = [t(lang, "top.cats_title", period=period_label(lang, start, end, today)), ""]
        for i, c in enumerate(cats[:10], start=1):
            lines.append(f"{i}. {c['emoji'] or '➕'} {esc(category_name(c if c['id'] else None, lang))}: "
                         f"<b>{money(user, c['total'])}</b> ({c['total'] / total * 100:.0f}%)")
        await message.answer("\n".join(lines))
        return
    rows, _, n = service.query_expenses(db, user["telegram_id"], start=start, end=end, limit=10, order="amount")
    if n == 0:
        await message.answer(t(lang, "sum.empty", period=period_label(lang, start, end, today)))
        return
    lines = [t(lang, "top.title", period=period_label(lang, start, end, today)), ""]
    lines += [f"{i}. {entry_line(user, lang, e)}" for i, e in enumerate(rows, start=1)]
    await message.answer("\n".join(lines))


# ---------------------------------------------------------------- /stats and charts
@router.message(Command("stats"))
async def cmd_stats(message: Message, db, user, lang: str) -> None:
    today = service.user_today(user)
    lines = stats.insight_lines(db, user, today)
    if not lines:
        await message.answer(t(lang, "stats.empty"))
        return
    await message.answer(
        t(lang, "stats.title") + "\n\n" + "\n".join(f"• {x}" for x in lines),
        reply_markup=kb([[(t(lang, "chart.btn_monthly"), "chart:month"), (t(lang, "chart.btn_category"), "chart:cat")],
                         [(t(lang, "chart.btn_weekday"), "chart:wd")]]))


@router.message(Command("chart"))
async def cmd_chart(message: Message, db, user, lang: str) -> None:
    await message.answer(
        t(lang, "chart.pick"),
        reply_markup=kb([[(t(lang, "chart.btn_monthly"), "chart:month"), (t(lang, "chart.btn_category"), "chart:cat")],
                         [(t(lang, "chart.btn_weekday"), "chart:wd")]]))


@router.callback_query(F.data.startswith("chart:"))
async def on_chart(cb: CallbackQuery, db, user, lang: str) -> None:
    kind = cb.data.split(":", 1)[1]
    today = service.user_today(user)
    await cb.answer()
    if kind == "month":
        png = charts.monthly_chart(db, user, today)
    elif kind == "cat":
        first, last = month_bounds(today)
        if stats.period_total(db, user["telegram_id"], first, last) <= 0:
            await cb.message.answer(t(lang, "stats.empty"))
            return
        png = charts.category_chart(db, user, first, last)
    else:
        png = charts.weekday_chart(db, user, today)
    await cb.message.answer_photo(BufferedInputFile(png, filename="chart.png"))


# ---------------------------------------------------------------------- /export
@router.message(Command("export"))
async def cmd_export(message: Message, command: CommandObject, db, user, lang: str) -> None:
    today = service.user_today(user)
    period, _ = parse_period((command.args or "").split(), today)
    start, end = (period.start, period.end) if period else month_bounds(today)
    if period and period.kind == "all":
        first = db.scalar("SELECT MIN(spent_on) FROM expenses WHERE user_id = ?", (user["telegram_id"],))
        start = date.fromisoformat(first) if first else today
        end = today
    data = exports.build_workbook(db, user, start, end)
    name = f"moneymate_{start:%Y%m%d}_{end:%Y%m%d}.xlsx"
    await message.answer_document(
        BufferedInputFile(data, filename=name),
        caption=t(lang, "export.caption", period=period_label(lang, start, end, today)))


# ----------------------------------------------------------- monthly report (scheduler)
async def send_monthly_report(bot: Bot, db, user, first: date, last: date) -> None:
    """Chart + summary + Excel file for one month. Telegram bots cannot write to a user's
    'Saved Messages', so the report arrives in the bot chat with a hint to forward it."""
    tid, lang = user["telegram_id"], user["language"]
    today = service.user_today(user)
    total = stats.period_total(db, tid, first, last)
    if total > 0:
        await bot.send_message(tid, t(lang, "report.intro", month=period_label(lang, first, last, today)))
        await bot.send_message(tid, summary_text(db, user, first, last, today))
        await bot.send_photo(tid, BufferedInputFile(charts.category_chart(db, user, first, last), filename="categories.png"))
        data = exports.build_workbook(db, user, first, last)
        await bot.send_document(
            tid, BufferedInputFile(data, filename=f"moneymate_{month_key(first)}.xlsx"),
            caption=t(lang, "report.forward_hint"))
    else:
        await bot.send_message(tid, t(lang, "report.empty", month=period_label(lang, first, last, today)))
    service.update_user(db, tid, last_report_month=month_key(first))
