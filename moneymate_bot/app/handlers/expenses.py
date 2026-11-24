"""Adding expenses: one-line entry ("taxi 22k yesterday") and the guided flow for a bare number."""
from __future__ import annotations

from datetime import date, timedelta

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import config, service
from ..i18n import bucket_name, category_name, t
from ..keyboards import categories_kb, date_kb, kb, skip_kb
from ..parser import parse_message
from ..utils import format_money
from .common import AddExpense, esc, fmt_date, money, safe_edit

router = Router(name="expenses")
router.message.filter(F.chat.type == "private")

DATE_HINT = "dd.mm"


# ------------------------------------------------------------------- saving + replies
async def save_and_confirm(message: Message, db, user, amount: float, category_id: int | None,
                           note: str, spent_on: date) -> None:
    lang = user["language"]
    eid = service.add_expense(db, user["telegram_id"], amount, category_id, note, spent_on)
    exp = service.get_expense(db, user["telegram_id"], eid)
    cat = service.get_category(db, user["telegram_id"], exp["category_id"]) if exp["category_id"] else None
    first, last = _month(spent_on)
    bal = service.bucket_balances(db, user["telegram_id"], first, last)[exp["bucket"]]
    lines = [t(lang, "exp.saved",
               emoji=cat["emoji"] if cat else "➕",
               amount=money(user, amount),
               category=esc(category_name(cat, lang)),
               date=fmt_date(spent_on),
               bucket=bucket_name(lang, exp["bucket"]))]
    if note:
        lines.append(f"📝 {esc(note)}")
    if bal["allocated"] > 0:
        lines.append(t(lang, "exp.bucket_left", bucket=bucket_name(lang, exp["bucket"]),
                       left=money(user, bal["left"])))
        if bal["left"] < 0:
            lines.append(t(lang, "alert.over", bucket=bucket_name(lang, exp["bucket"]),
                           amount=money(user, -bal["left"])))
        elif bal["allocated"] and bal["left"] <= bal["allocated"] * 0.2:
            lines.append(t(lang, "alert.low", bucket=bucket_name(lang, exp["bucket"]),
                           left=money(user, bal["left"])))
    await message.answer(
        "\n".join(lines),
        reply_markup=kb([[(t(lang, "btn.change_category"), f"exp_cat:{eid}"),
                          (t(lang, "btn.undo"), f"exp_del:{eid}")]]),
    )


def _month(d: date) -> tuple[date, date]:
    from ..utils import month_bounds
    return month_bounds(d)


# ------------------------------------------------------------------ the catch-all entry
@router.message(StateFilter(None), F.text, ~F.text.startswith("/"))
async def on_text(message: Message, state: FSMContext, db, user, lang: str) -> None:
    if not user["onboarded"]:
        await message.answer(t(lang, "need_start"))
        return
    today = service.user_today(user)
    parsed = parse_message(message.text, today)
    if parsed.amount is None:
        await message.answer(t(lang, "exp.not_understood"))
        return
    if parsed.is_income:
        from .income import start_income
        await start_income(message, state, db, user, parsed.amount, parsed.note, parsed.date or today)
        return

    cat = service.resolve_category(db, user["telegram_id"], parsed.note)
    if cat is not None and parsed.note:
        await save_and_confirm(message, db, user, parsed.amount, cat["id"], parsed.note, parsed.date or today)
        return

    # Category unknown (a bare number, or a word we do not recognise): ask.
    await state.update_data(amount=parsed.amount, note=parsed.note,
                            date=parsed.date.isoformat() if parsed.date else None)
    if not user["guided_mode"] and parsed.note:
        # guided mode off: file under "other" straight away
        other = service.category_by_key(db, user["telegram_id"], "other")
        await state.clear()
        await save_and_confirm(message, db, user, parsed.amount, other["id"] if other else None,
                               parsed.note, parsed.date or today)
        return
    await state.set_state(AddExpense.category)
    await message.answer(
        t(lang, "exp.ask_category", amount=money(user, parsed.amount)),
        reply_markup=_with_cancel(categories_kb(db, user["telegram_id"], lang, "g_cat"), lang),
    )


def _with_cancel(markup, lang: str):
    from aiogram.types import InlineKeyboardButton
    markup.inline_keyboard.append([InlineKeyboardButton(text=t(lang, "btn.cancel"), callback_data="g_cancel")])
    return markup


@router.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext, lang: str) -> None:
    await state.clear()
    await message.answer(t(lang, "exp.add_help"))


# ----------------------------------------------------------------------- guided flow
@router.callback_query(F.data == "g_cancel")
async def guided_cancel(cb: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.clear()
    await cb.answer()
    await safe_edit(cb.message, t(lang, "cancelled"))


@router.callback_query(F.data.startswith("g_cat:"), AddExpense.category)
async def guided_category(cb: CallbackQuery, state: FSMContext, db, user, lang: str) -> None:
    cid = int(cb.data.split(":", 1)[1])
    if service.get_category(db, user["telegram_id"], cid) is None:
        await cb.answer()
        return
    await state.update_data(category_id=cid)
    await cb.answer()
    data = await state.get_data()
    if data.get("date"):
        await _ask_note_or_save(cb.message, state, db, user, lang)
        return
    await state.set_state(AddExpense.date)
    await safe_edit(cb.message, t(lang, "exp.ask_date"), date_kb(lang))


@router.callback_query(F.data.startswith("date:"), AddExpense.date)
async def guided_date(cb: CallbackQuery, state: FSMContext, db, user, lang: str) -> None:
    choice = cb.data.split(":", 1)[1]
    today = service.user_today(user)
    await cb.answer()
    if choice == "pick":
        await state.set_state(AddExpense.date_text)
        await safe_edit(cb.message, t(lang, "exp.type_date", hint=DATE_HINT))
        return
    d = today if choice == "today" else today - timedelta(days=1)
    await state.update_data(date=d.isoformat())
    await _ask_note_or_save(cb.message, state, db, user, lang)


@router.message(AddExpense.date_text, F.text, ~F.text.startswith("/"))
async def guided_date_text(message: Message, state: FSMContext, db, user, lang: str) -> None:
    today = service.user_today(user)
    parsed = parse_message(message.text, today)
    if parsed.date is None or parsed.date > today:
        await message.answer(t(lang, "exp.bad_date", hint=DATE_HINT))
        return
    await state.update_data(date=parsed.date.isoformat())
    await _ask_note_or_save(message, state, db, user, lang)


async def _ask_note_or_save(message: Message, state: FSMContext, db, user, lang: str) -> None:
    data = await state.get_data()
    if data.get("note") or not user["guided_mode"]:
        await _finish(message, state, db, user)
        return
    await state.set_state(AddExpense.note)
    await message.answer(t(lang, "exp.ask_note"), reply_markup=skip_kb(lang, "g_note_skip"))


@router.callback_query(F.data == "g_note_skip", AddExpense.note)
async def guided_note_skip(cb: CallbackQuery, state: FSMContext, db, user) -> None:
    await cb.answer()
    await _finish(cb.message, state, db, user)


@router.message(AddExpense.note, F.text, ~F.text.startswith("/"))
async def guided_note(message: Message, state: FSMContext, db, user) -> None:
    await state.update_data(note=message.text.strip()[:200])
    await _finish(message, state, db, user)


async def _finish(message: Message, state: FSMContext, db, user) -> None:
    data = await state.get_data()
    await state.clear()
    today = service.user_today(user)
    spent_on = date.fromisoformat(data["date"]) if data.get("date") else today
    await save_and_confirm(message, db, user, float(data["amount"]), data.get("category_id"),
                           data.get("note") or "", spent_on)


# ---------------------------------------------------------- undo / change category
@router.message(Command("undo"))
async def cmd_undo(message: Message, db, user, lang: str) -> None:
    tid = user["telegram_id"]
    last_e, last_i = service.last_expense(db, tid), service.last_income(db, tid)
    # undo whichever was created most recently
    if last_i and (last_e is None or last_i["created_at"] > last_e["created_at"]):
        service.delete_income(db, tid, last_i["id"])
        await message.answer(t(lang, "undo.income", amount=money(user, last_i["amount"])))
    elif last_e:
        service.delete_expense(db, tid, last_e["id"])
        cat = {"key": last_e["cat_key"], "name": last_e["cat_name"]} if last_e["category_id"] else None
        await message.answer(t(lang, "undo.expense", amount=money(user, last_e["amount"]),
                               note=esc(last_e["note"] or category_name(cat, lang))))
    else:
        await message.answer(t(lang, "undo.nothing"))


@router.callback_query(F.data.startswith("exp_del:"))
async def on_delete(cb: CallbackQuery, db, user, lang: str) -> None:
    eid = int(cb.data.split(":", 1)[1])
    ok = service.delete_expense(db, user["telegram_id"], eid)
    await cb.answer(t(lang, "undo.done") if ok else t(lang, "undo.nothing"))
    await safe_edit(cb.message, cb.message.html_text + "\n\n" + t(lang, "undo.deleted_mark")
                    if ok else cb.message.html_text)


@router.callback_query(F.data.startswith("exp_cat:"))
async def on_change_category(cb: CallbackQuery, db, user, lang: str) -> None:
    eid = int(cb.data.split(":", 1)[1])
    if service.get_expense(db, user["telegram_id"], eid) is None:
        await cb.answer(t(lang, "undo.nothing"))
        return
    await cb.answer()
    await cb.message.answer(t(lang, "exp.pick_new_category"),
                            reply_markup=categories_kb(db, user["telegram_id"], lang, f"exp_set:{eid}"))


@router.callback_query(F.data.startswith("exp_set:"))
async def on_set_category(cb: CallbackQuery, db, user, lang: str) -> None:
    _, eid, cid = cb.data.split(":")
    ok = service.set_expense_category(db, user["telegram_id"], int(eid), int(cid))
    await cb.answer(t(lang, "exp.category_changed") if ok else t(lang, "undo.nothing"))
    if ok:
        await safe_edit(cb.message, t(lang, "exp.category_changed"))


# Must stay the LAST text handler of the LAST router. Plain text with no active flow is taken by
# on_text above, and every flow that expects typed text has its own handler, so a message that
# reaches this one is text typed while a flow is waiting for a button press.
@router.message(F.text, ~F.text.startswith("/"))
async def text_during_button_step(message: Message, lang: str) -> None:
    await message.answer(t(lang, "flow.use_buttons"))
