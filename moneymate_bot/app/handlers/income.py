"""Income: log a paycheck, then split it into Needs / Wants / Savings by percentage."""
from __future__ import annotations

from datetime import date

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import config, service
from ..i18n import bucket_name, t
from ..keyboards import kb
from ..parser import parse_message
from ..utils import parse_percent_list
from .common import IncomeFlow, esc, money, safe_edit

router = Router(name="income")
router.message.filter(F.chat.type == "private")


def _pct(p: float) -> str:
    return f"{p:g}"


def _split_text(lang: str, user, amount: float, percents: tuple | list) -> str:
    shares = service.split_amounts(amount, percents)
    lines = [t(lang, "inc.split_preview", amount=money(user, amount))]
    for b, p, s in zip(config.BUCKETS, percents, shares):
        lines.append(f"• {bucket_name(lang, b)}: {_pct(p)}% = {money(user, s)}")
    return "\n".join(lines)


def _choose_kb(lang: str, user):
    usual = service.get_split(user)
    rows = [[(t(lang, "inc.use_usual", split="/".join(str(x) for x in usual)), "inc_pick:usual")]]
    tpl = [(("/".join(str(x) for x in v)), f"inc_pick:{k}") for k, v in config.SPLIT_TEMPLATES.items()]
    rows.append(tpl[:2])
    rows.append(tpl[2:])
    rows.append([(t(lang, "inc.custom"), "inc_custom")])
    rows.append([(t(lang, "btn.cancel"), "inc_cancel")])
    return kb(rows)


async def start_income(message: Message, state: FSMContext, db, user, amount: float,
                       source: str, received_on: date) -> None:
    lang = user["language"]
    await state.set_state(IncomeFlow.choose)
    await state.update_data(amount=amount, source=source, date=received_on.isoformat(), percents=None)
    await message.answer(
        t(lang, "inc.ask_split", amount=money(user, amount), source=esc(source or "—")),
        reply_markup=_choose_kb(lang, user),
    )


@router.message(Command("income"))
async def cmd_income(message: Message, state: FSMContext, user, lang: str) -> None:
    await state.clear()
    await state.set_state(IncomeFlow.amount)
    await message.answer(t(lang, "inc.ask_amount"))


@router.message(IncomeFlow.amount, F.text, ~F.text.startswith("/"))
async def income_amount(message: Message, state: FSMContext, db, user, lang: str) -> None:
    today = service.user_today(user)
    p = parse_message(message.text, today)
    if p.amount is None:
        await message.answer(t(lang, "ob.bad_number"))
        return
    await start_income(message, state, db, user, p.amount, p.note, p.date or today)


@router.callback_query(F.data == "inc_cancel")
async def inc_cancel(cb: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.clear()
    await cb.answer()
    await safe_edit(cb.message, t(lang, "cancelled"))


async def _show_confirmation(message: Message, state: FSMContext, user, lang: str,
                             percents: list, edit: bool) -> None:
    data = await state.get_data()
    await state.update_data(percents=list(percents))
    text = _split_text(lang, user, float(data["amount"]), percents)
    usual = list(service.get_split(user))
    rows = [[(t(lang, "btn.confirm"), "inc_ok")]]
    if [float(x) for x in percents] != [float(x) for x in usual]:
        rows.append([(t(lang, "inc.confirm_save"), "inc_ok_save")])
    rows.append([(t(lang, "btn.edit"), "inc_custom"), (t(lang, "btn.cancel"), "inc_cancel")])
    if edit:
        await safe_edit(message, text, kb(rows))
    else:
        await message.answer(text, reply_markup=kb(rows))


@router.callback_query(F.data.startswith("inc_pick:"), IncomeFlow.choose)
async def inc_pick(cb: CallbackQuery, state: FSMContext, user, lang: str) -> None:
    key = cb.data.split(":", 1)[1]
    percents = service.get_split(user) if key == "usual" else config.SPLIT_TEMPLATES.get(key)
    await cb.answer()
    if percents is None or not (await state.get_data()).get("amount"):
        return
    await _show_confirmation(cb.message, state, user, lang, list(percents), edit=True)


@router.callback_query(F.data == "inc_custom")
async def inc_custom(cb: CallbackQuery, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    if not data.get("amount"):
        await cb.answer()
        return
    await state.set_state(IncomeFlow.custom)
    await cb.answer()
    await cb.message.answer(t(lang, "inc.ask_custom"))


@router.message(IncomeFlow.custom, F.text, ~F.text.startswith("/"))
async def inc_custom_text(message: Message, state: FSMContext, user, lang: str) -> None:
    nums = parse_percent_list(message.text)
    if nums is None or len(nums) not in (2, 3) or any(n < 0 for n in nums):
        await message.answer(t(lang, "inc.bad_custom"))
        return
    if len(nums) == 2:  # the last bucket (savings) takes the remainder
        nums.append(round(100 - sum(nums), 4))
    if nums[2] < 0 or abs(sum(nums) - 100) > 0.01:
        await message.answer(t(lang, "inc.bad_sum", total=_pct(round(sum(nums), 2))))
        return
    await state.set_state(IncomeFlow.choose)
    await _show_confirmation(message, state, user, lang, nums, edit=False)


async def _confirm(cb: CallbackQuery, state: FSMContext, db, user, lang: str, save_default: bool) -> None:
    data = await state.get_data()
    percents = data.get("percents")
    if not data.get("amount") or not percents:
        await cb.answer()
        return
    tid = user["telegram_id"]
    amount = float(data["amount"])
    service.add_income(db, tid, amount, data.get("source") or "", date.fromisoformat(data["date"]), percents)
    if save_default:
        service.update_user(db, tid, split=",".join(_pct(p) for p in percents))
    await state.clear()
    await cb.answer()
    shares = service.split_amounts(amount, percents)
    lines = [t(lang, "inc.saved", amount=money(user, amount))]
    for b, p, s in zip(config.BUCKETS, percents, shares):
        lines.append(f"• {bucket_name(lang, b)}: {money(user, s)} ({_pct(p)}%)")
    lines.append("")
    lines.append(t(lang, "inc.saved_hint"))
    await safe_edit(cb.message, "\n".join(lines))


@router.callback_query(F.data == "inc_ok", IncomeFlow.choose)
async def inc_ok(cb: CallbackQuery, state: FSMContext, db, user, lang: str) -> None:
    await _confirm(cb, state, db, user, lang, save_default=False)


@router.callback_query(F.data == "inc_ok_save", IncomeFlow.choose)
async def inc_ok_save(cb: CallbackQuery, state: FSMContext, db, user, lang: str) -> None:
    await _confirm(cb, state, db, user, lang, save_default=True)
