"""/start: welcome banner, language, currency, then the getting-to-know-you questions.
Every question can be skipped. Answers are stored in the `profiles` table and used to
personalise tips and the default budget split."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from .. import config, service
from ..i18n import t
from ..keyboards import kb, language_kb, skip_kb
from ..parser import parse_message
from .common import Onboarding, esc, money

router = Router(name="onboarding")
router.message.filter(F.chat.type == "private")

JOBS = ["student", "employed", "self", "business", "other"]
GOALS = ["save", "debt", "track", "emergency"]


async def send_banner(message: Message, caption: str, markup=None) -> None:
    if config.BANNER_PATH.exists():
        await message.answer_photo(FSInputFile(config.BANNER_PATH), caption=caption, reply_markup=markup)
    else:
        await message.answer(caption, reply_markup=markup)


async def begin_questions(message: Message, state: FSMContext, lang: str, tg_first_name: str) -> None:
    """Ask for the user's name (first question). Also used by /profile to redo the questions."""
    await state.set_state(Onboarding.name)
    await message.answer(
        t(lang, "ob.ask_name"),
        reply_markup=kb([[(t(lang, "ob.use_name", name=esc(tg_first_name)), "ob_name_tg")]]),
    )


async def step_age(message: Message, state: FSMContext, lang: str) -> None:
    await state.set_state(Onboarding.age)
    await message.answer(t(lang, "ob.ask_age"), reply_markup=skip_kb(lang))


async def step_job(message: Message, state: FSMContext, lang: str) -> None:
    await state.set_state(Onboarding.job)
    rows = [[(t(lang, f"ob.job.{j}"), f"ob_job:{j}")] for j in JOBS]
    rows.append([(t(lang, "btn.skip"), "ob_skip")])
    await message.answer(t(lang, "ob.ask_job"), reply_markup=kb(rows))


async def step_income(message: Message, state: FSMContext, lang: str, is_student: bool) -> None:
    await state.set_state(Onboarding.income)
    key = "ob.ask_income_student" if is_student else "ob.ask_income"
    await message.answer(t(lang, key), reply_markup=skip_kb(lang))


async def step_debt(message: Message, state: FSMContext, lang: str) -> None:
    await state.set_state(Onboarding.debt)
    await message.answer(
        t(lang, "ob.ask_debt"),
        reply_markup=kb([[(t(lang, "btn.yes"), "ob_debt:yes"), (t(lang, "btn.no"), "ob_debt:no")],
                         [(t(lang, "btn.skip"), "ob_skip")]]),
    )


async def step_debt_total(message: Message, state: FSMContext, lang: str) -> None:
    await state.set_state(Onboarding.debt_total)
    await message.answer(t(lang, "ob.ask_debt_total"), reply_markup=skip_kb(lang))


async def step_debt_monthly(message: Message, state: FSMContext, lang: str) -> None:
    await state.set_state(Onboarding.debt_monthly)
    await message.answer(t(lang, "ob.ask_debt_monthly"), reply_markup=skip_kb(lang))


async def step_goal(message: Message, state: FSMContext, lang: str) -> None:
    await state.set_state(Onboarding.goal)
    rows = [[(t(lang, f"ob.goal.{g}"), f"ob_goal:{g}")] for g in GOALS]
    rows.append([(t(lang, "btn.skip"), "ob_skip")])
    await message.answer(t(lang, "ob.ask_goal"), reply_markup=kb(rows))


async def finish(message: Message, state: FSMContext, db, tid: int) -> None:
    await state.clear()
    service.update_user(db, tid, onboarded=1)
    user = service.get_user(db, tid)
    lang = user["language"]
    p = service.get_profile(db, tid)
    lines = [t(lang, "ob.done_title", name=esc(user["name"] or ""))]
    if p:
        if p["age"]:
            lines.append(t(lang, "ob.sum_age", age=p["age"]))
        if p["occupation"]:
            lines.append(t(lang, "ob.sum_job", job=t(lang, f"ob.job.{p['occupation']}")))
        if p["income"]:
            lines.append(t(lang, "ob.sum_income", amount=money(user, p["income"])))
        if p["debt_total"]:
            lines.append(t(lang, "ob.sum_debt", amount=money(user, p["debt_total"])))
        if p["goal"]:
            lines.append(t(lang, "ob.sum_goal", goal=t(lang, f"ob.goal.{p['goal']}")))
    lines.append("")
    lines.append(t(lang, "ob.privacy"))
    await message.answer("\n".join(lines))
    await message.answer(t(lang, "ob.tour"))


# --------------------------------------------------------------------------- /start
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, user, lang: str) -> None:
    await state.clear()
    if user["onboarded"]:
        await message.answer(t(lang, "welcome_back", name=esc(user["name"] or "")))
        return
    await send_banner(message, t(lang, "ob.pick_language"), language_kb("ob_lang"))


@router.callback_query(F.data.startswith("ob_lang:"))
async def on_language(cb: CallbackQuery, db, user) -> None:
    lang = cb.data.split(":", 1)[1]
    if lang not in config.LANGUAGES:
        await cb.answer()
        return
    service.update_user(db, user["telegram_id"], language=lang)
    await cb.answer()
    rows = [[(c, f"ob_cur:{c}") for c in config.CURRENCIES]]
    await cb.message.answer(t(lang, "ob.ask_currency"), reply_markup=kb(rows))


@router.callback_query(F.data.startswith("ob_cur:"))
async def on_currency(cb: CallbackQuery, state: FSMContext, db, user) -> None:
    cur = cb.data.split(":", 1)[1]
    if cur not in config.CURRENCIES:
        await cb.answer()
        return
    service.update_user(db, user["telegram_id"], currency=cur)
    await cb.answer()
    lang = service.get_user(db, user["telegram_id"])["language"]
    await begin_questions(cb.message, state, lang, cb.from_user.first_name or "")


# ---------------------------------------------------------------------------- name
async def _save_name(message: Message, state: FSMContext, db, tid: int, name: str) -> None:
    name = name.strip()[:40]
    service.update_user(db, tid, name=name)
    lang = service.get_user(db, tid)["language"]
    await message.answer(t(lang, "ob.nice_to_meet", name=esc(name)))
    await step_age(message, state, lang)


@router.callback_query(F.data == "ob_name_tg", Onboarding.name)
async def name_from_telegram(cb: CallbackQuery, state: FSMContext, db, user) -> None:
    await cb.answer()
    await _save_name(cb.message, state, db, user["telegram_id"], cb.from_user.first_name or "")


@router.message(Onboarding.name, F.text, ~F.text.startswith("/"))
async def name_typed(message: Message, state: FSMContext, db, user) -> None:
    await _save_name(message, state, db, user["telegram_id"], message.text)


# ----------------------------------------------------------------------------- age
@router.message(Onboarding.age, F.text, ~F.text.startswith("/"))
async def age_typed(message: Message, state: FSMContext, db, user, lang: str) -> None:
    digits = "".join(ch for ch in message.text if ch.isdigit())
    if not digits or not 10 <= int(digits) <= 100:
        await message.answer(t(lang, "ob.bad_age"), reply_markup=skip_kb(lang))
        return
    service.save_profile(db, user["telegram_id"], age=int(digits))
    await step_job(message, state, lang)


# ------------------------------------------------------------------------------ job
@router.callback_query(F.data.startswith("ob_job:"), Onboarding.job)
async def job_chosen(cb: CallbackQuery, state: FSMContext, db, user, lang: str) -> None:
    job = cb.data.split(":", 1)[1]
    if job not in JOBS:
        await cb.answer()
        return
    service.save_profile(db, user["telegram_id"], occupation=job, is_student=1 if job == "student" else 0)
    await cb.answer()
    await step_income(cb.message, state, lang, is_student=(job == "student"))


# --------------------------------------------------------------------------- income
async def _amount_from_text(message: Message, user) -> float | None:
    return parse_message(message.text, service.user_today(user)).amount


@router.message(Onboarding.income, F.text, ~F.text.startswith("/"))
async def income_typed(message: Message, state: FSMContext, db, user, lang: str) -> None:
    amount = await _amount_from_text(message, user)
    if amount is None:
        await message.answer(t(lang, "ob.bad_number"), reply_markup=skip_kb(lang))
        return
    service.save_profile(db, user["telegram_id"], income=amount)
    await step_debt(message, state, lang)


# ---------------------------------------------------------------------------- debts
@router.callback_query(F.data.startswith("ob_debt:"), Onboarding.debt)
async def debt_choice(cb: CallbackQuery, state: FSMContext, db, user, lang: str) -> None:
    await cb.answer()
    if cb.data.endswith(":yes"):
        await step_debt_total(cb.message, state, lang)
    else:
        service.save_profile(db, user["telegram_id"], debt_total=0, debt_monthly=0)
        await step_goal(cb.message, state, lang)


@router.message(Onboarding.debt_total, F.text, ~F.text.startswith("/"))
async def debt_total_typed(message: Message, state: FSMContext, db, user, lang: str) -> None:
    amount = await _amount_from_text(message, user)
    if amount is None:
        await message.answer(t(lang, "ob.bad_number"), reply_markup=skip_kb(lang))
        return
    service.save_profile(db, user["telegram_id"], debt_total=amount)
    await step_debt_monthly(message, state, lang)


@router.message(Onboarding.debt_monthly, F.text, ~F.text.startswith("/"))
async def debt_monthly_typed(message: Message, state: FSMContext, db, user, lang: str) -> None:
    amount = await _amount_from_text(message, user)
    if amount is None:
        await message.answer(t(lang, "ob.bad_number"), reply_markup=skip_kb(lang))
        return
    service.save_profile(db, user["telegram_id"], debt_monthly=amount)
    await step_goal(message, state, lang)


# ----------------------------------------------------------------------------- goal
@router.callback_query(F.data.startswith("ob_goal:"), Onboarding.goal)
async def goal_chosen(cb: CallbackQuery, state: FSMContext, db, user) -> None:
    goal = cb.data.split(":", 1)[1]
    if goal in GOALS:
        service.save_profile(db, user["telegram_id"], goal=goal)
    await cb.answer()
    await finish(cb.message, state, db, user["telegram_id"])


# ----------------------------------------------------------------------------- skip
@router.callback_query(F.data == "ob_skip")
async def skip_step(cb: CallbackQuery, state: FSMContext, db, user, lang: str) -> None:
    """One Skip button for every question: move on to whatever comes next."""
    current = await state.get_state()
    await cb.answer()
    msg = cb.message
    if current == Onboarding.age.state:
        await step_job(msg, state, lang)
    elif current == Onboarding.job.state:
        await step_income(msg, state, lang, is_student=False)
    elif current == Onboarding.income.state:
        await step_debt(msg, state, lang)
    elif current == Onboarding.debt.state:
        await step_goal(msg, state, lang)
    elif current in (Onboarding.debt_total.state, Onboarding.debt_monthly.state):
        await step_goal(msg, state, lang)
    elif current == Onboarding.goal.state:
        await finish(msg, state, db, user["telegram_id"])
