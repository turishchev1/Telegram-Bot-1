"""Settings, profile, help, custom categories and data deletion."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import config, service
from ..i18n import t
from ..keyboards import kb, language_kb
from ..utils import parse_hhmm, parse_percent_list, valid_timezone
from .common import SettingsFlow, esc, money, safe_edit

router = Router(name="settings")
router.message.filter(F.chat.type == "private")

COMMON_TIMEZONES = [
    ("Tashkent", "Asia/Tashkent"), ("Moscow", "Europe/Moscow"), ("Almaty", "Asia/Almaty"),
    ("Istanbul", "Europe/Istanbul"), ("London", "Europe/London"), ("New York", "America/New_York"),
]


def _onoff(lang: str, value) -> str:
    return t(lang, "on") if value else t(lang, "off")


def settings_text(user) -> str:
    lang = user["language"]
    split = "/".join(str(x) for x in service.get_split(user))
    return "\n".join([
        t(lang, "set.title"),
        "",
        t(lang, "set.language", v=config.LANGUAGES[lang]),
        t(lang, "set.currency", v=user["currency"]),
        t(lang, "set.timezone", v=esc(user["timezone"])),
        t(lang, "set.split", v=split),
        t(lang, "set.tips", v=_onoff(lang, user["tips_enabled"]), time=user["tip_time"]),
        t(lang, "set.guided", v=_onoff(lang, user["guided_mode"])),
        t(lang, "set.reminders", v=_onoff(lang, user["reminders_enabled"])),
    ])


def settings_kb(user):
    lang = user["language"]
    return kb([
        [(t(lang, "btn.language"), "set:lang"), (t(lang, "btn.currency"), "set:cur")],
        [(t(lang, "btn.timezone"), "set:tz"), (t(lang, "btn.tiptime"), "set:tiptime")],
        [(t(lang, "btn.toggle_tips"), "tg:tips"), (t(lang, "btn.toggle_guided"), "tg:guided")],
        [(t(lang, "btn.toggle_reminders"), "tg:remind")],
        [(t(lang, "btn.profile"), "set:profile"), (t(lang, "btn.new_category"), "set:newcat")],
    ])


# -------------------------------------------------------------------- help / cancel
@router.message(Command("help"))
async def cmd_help(message: Message, lang: str) -> None:
    await message.answer(t(lang, "help.text"))


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, lang: str) -> None:
    await state.clear()
    await message.answer(t(lang, "cancelled"))


# ------------------------------------------------------------------------ settings
@router.message(Command("settings"))
async def cmd_settings(message: Message, user) -> None:
    await message.answer(settings_text(user), reply_markup=settings_kb(user))


async def _refresh(cb: CallbackQuery, db, tid: int) -> None:
    user = service.get_user(db, tid)
    await safe_edit(cb.message, settings_text(user), settings_kb(user))


@router.callback_query(F.data.startswith("tg:"))
async def on_toggle(cb: CallbackQuery, db, user, lang: str) -> None:
    what = cb.data.split(":", 1)[1]
    field = {"tips": "tips_enabled", "guided": "guided_mode", "remind": "reminders_enabled"}.get(what)
    if not field:
        await cb.answer()
        return
    service.update_user(db, user["telegram_id"], **{field: 0 if user[field] else 1})
    await cb.answer()
    await _refresh(cb, db, user["telegram_id"])


# ---------------------------------------------------------------- language / currency
@router.message(Command("language"))
async def cmd_language(message: Message, lang: str) -> None:
    await message.answer(t(lang, "set.pick_language"), reply_markup=language_kb("set_lang"))


@router.callback_query(F.data == "set:lang")
async def on_language_menu(cb: CallbackQuery, lang: str) -> None:
    await cb.answer()
    await cb.message.answer(t(lang, "set.pick_language"), reply_markup=language_kb("set_lang"))


@router.callback_query(F.data.startswith("set_lang:"))
async def on_language_set(cb: CallbackQuery, db, user) -> None:
    code = cb.data.split(":", 1)[1]
    if code not in config.LANGUAGES:
        await cb.answer()
        return
    service.update_user(db, user["telegram_id"], language=code)
    await cb.answer()
    await safe_edit(cb.message, t(code, "set.language_changed"))


@router.message(Command("currency"))
async def cmd_currency(message: Message, lang: str) -> None:
    await message.answer(t(lang, "set.pick_currency"),
                         reply_markup=kb([[(c, f"set_cur:{c}") for c in config.CURRENCIES]]))


@router.callback_query(F.data == "set:cur")
async def on_currency_menu(cb: CallbackQuery, lang: str) -> None:
    await cb.answer()
    await cb.message.answer(t(lang, "set.pick_currency"),
                            reply_markup=kb([[(c, f"set_cur:{c}") for c in config.CURRENCIES]]))


@router.callback_query(F.data.startswith("set_cur:"))
async def on_currency_set(cb: CallbackQuery, db, user, lang: str) -> None:
    cur = cb.data.split(":", 1)[1]
    if cur not in config.CURRENCIES:
        await cb.answer()
        return
    service.update_user(db, user["telegram_id"], currency=cur)
    await cb.answer()
    await safe_edit(cb.message, t(lang, "set.currency_changed", v=cur))


# ------------------------------------------------------------------------ timezone
def _tz_kb():
    rows = [[(name, f"set_tz:{tz}") for name, tz in COMMON_TIMEZONES[i:i + 3]] for i in range(0, 6, 3)]
    rows.append([("✏️ …", "set_tz:other")])
    return kb(rows)


@router.message(Command("timezone"))
async def cmd_timezone(message: Message, lang: str) -> None:
    await message.answer(t(lang, "set.pick_tz"), reply_markup=_tz_kb())


@router.callback_query(F.data == "set:tz")
async def on_tz_menu(cb: CallbackQuery, lang: str) -> None:
    await cb.answer()
    await cb.message.answer(t(lang, "set.pick_tz"), reply_markup=_tz_kb())


@router.callback_query(F.data.startswith("set_tz:"))
async def on_tz_set(cb: CallbackQuery, state: FSMContext, db, user, lang: str) -> None:
    tz = cb.data.split(":", 1)[1]
    await cb.answer()
    if tz == "other":
        await state.set_state(SettingsFlow.timezone)
        await cb.message.answer(t(lang, "set.type_tz"))
        return
    if valid_timezone(tz):
        service.update_user(db, user["telegram_id"], timezone=tz)
        await safe_edit(cb.message, t(lang, "set.tz_changed", v=esc(tz)))


@router.message(SettingsFlow.timezone, F.text, ~F.text.startswith("/"))
async def tz_typed(message: Message, state: FSMContext, db, user, lang: str) -> None:
    tz = message.text.strip().replace(" ", "_")
    if not valid_timezone(tz):
        await message.answer(t(lang, "set.bad_tz"))
        return
    service.update_user(db, user["telegram_id"], timezone=tz)
    await state.clear()
    await message.answer(t(lang, "set.tz_changed", v=esc(tz)))


# ----------------------------------------------------------------------------- tips
@router.message(Command("tips"))
async def cmd_tips(message: Message, command: CommandObject, db, user, lang: str) -> None:
    arg = (command.args or "").strip().lower()
    if arg in ("on", "вкл", "yoq", "yoqish", "1"):
        service.update_user(db, user["telegram_id"], tips_enabled=1)
        await message.answer(t(lang, "tips.on", time=user["tip_time"]))
    elif arg in ("off", "выкл", "ochir", "o'chir", "0"):
        service.update_user(db, user["telegram_id"], tips_enabled=0)
        await message.answer(t(lang, "tips.off"))
    else:
        await message.answer(t(lang, "tips.help"))


@router.message(Command("tiptime"))
async def cmd_tiptime(message: Message, command: CommandObject, state: FSMContext, db, user, lang: str) -> None:
    arg = (command.args or "").strip()
    if not arg:
        await state.set_state(SettingsFlow.tip_time)
        await message.answer(t(lang, "tips.ask_time"))
        return
    await _set_tip_time(message, state, db, user, lang, arg)


@router.callback_query(F.data == "set:tiptime")
async def on_tiptime_menu(cb: CallbackQuery, state: FSMContext, lang: str) -> None:
    await cb.answer()
    await state.set_state(SettingsFlow.tip_time)
    await cb.message.answer(t(lang, "tips.ask_time"))


@router.message(SettingsFlow.tip_time, F.text, ~F.text.startswith("/"))
async def tiptime_typed(message: Message, state: FSMContext, db, user, lang: str) -> None:
    await _set_tip_time(message, state, db, user, lang, message.text)


async def _set_tip_time(message: Message, state: FSMContext, db, user, lang: str, text: str) -> None:
    hhmm = parse_hhmm(text)
    if hhmm is None:
        await message.answer(t(lang, "tips.bad_time"))
        return
    service.update_user(db, user["telegram_id"], tip_time=hhmm, tips_enabled=1)
    await state.clear()
    await message.answer(t(lang, "tips.time_set", time=hhmm))


@router.message(Command("tip"))
async def cmd_tip_now(message: Message, db, user, lang: str) -> None:
    from .. import tips
    tip = tips.pick_tip(db, user, service.user_today(user))
    if tip:
        tips.mark_sent(db, user["telegram_id"], tip["id"])
        await message.answer(t(lang, "tips.card", text=esc(tips.tip_text(tip, lang))))


# -------------------------------------------------------------------------- split
@router.message(Command("setsplit"))
async def cmd_setsplit(message: Message, command: CommandObject, db, user, lang: str) -> None:
    nums = parse_percent_list(command.args or "")
    if not nums or len(nums) not in (2, 3) or any(n < 0 for n in nums):
        await message.answer(t(lang, "split.help"))
        return
    if len(nums) == 2:
        nums.append(round(100 - sum(nums), 4))
    if nums[2] < 0 or abs(sum(nums) - 100) > 0.01:
        await message.answer(t(lang, "inc.bad_sum", total=f"{sum(nums):g}"))
        return
    service.update_user(db, user["telegram_id"], split=",".join(f"{n:g}" for n in nums))
    await message.answer(t(lang, "split.saved", v="/".join(f"{n:g}" for n in nums)))


# ------------------------------------------------------------------------- profile
@router.message(Command("profile"))
async def cmd_profile(message: Message, db, user, lang: str) -> None:
    await message.answer(_profile_text(db, user), reply_markup=kb([[(t(lang, "btn.redo_profile"), "set:profile")]]))


def _profile_text(db, user) -> str:
    lang = user["language"]
    p = service.get_profile(db, user["telegram_id"])
    unknown = "—"
    lines = [t(lang, "profile.title"), "", t(lang, "profile.name", v=esc(user["name"] or unknown))]
    if p:
        lines += [
            t(lang, "profile.age", v=p["age"] or unknown),
            t(lang, "profile.job", v=t(lang, f"ob.job.{p['occupation']}") if p["occupation"] else unknown),
            t(lang, "profile.income", v=money(user, p["income"]) if p["income"] else unknown),
            t(lang, "profile.debt", v=money(user, p["debt_total"]) if p["debt_total"] else t(lang, "profile.none")),
            t(lang, "profile.goal", v=t(lang, f"ob.goal.{p['goal']}") if p["goal"] else unknown),
        ]
    lines += ["", t(lang, "ob.privacy")]
    return "\n".join(lines)


@router.callback_query(F.data == "set:profile")
async def on_redo_profile(cb: CallbackQuery, state: FSMContext, lang: str) -> None:
    from .onboarding import begin_questions
    await cb.answer()
    await begin_questions(cb.message, state, lang, cb.from_user.first_name or "")


# ------------------------------------------------------------------ custom categories
def _split_emoji(text: str) -> tuple[str, str]:
    """'Pets 🐶' or '🐶 Pets' -> ('Pets', '🐶'). Default emoji is 🏷."""
    parts = text.split()
    emoji = "🏷"
    rest = []
    for p in parts:
        if not any(ch.isalnum() for ch in p) and len(p) <= 8 and emoji == "🏷":
            emoji = p
        else:
            rest.append(p)
    return " ".join(rest).strip(), emoji


@router.message(Command("newcategory"))
async def cmd_newcategory(message: Message, command: CommandObject, state: FSMContext, lang: str) -> None:
    arg = (command.args or "").strip()
    if not arg:
        await state.set_state(SettingsFlow.new_category)
        await message.answer(t(lang, "cat.ask_name"))
        return
    await _ask_bucket_for_category(message, state, lang, arg)


@router.callback_query(F.data == "set:newcat")
async def on_newcat_menu(cb: CallbackQuery, state: FSMContext, lang: str) -> None:
    await cb.answer()
    await state.set_state(SettingsFlow.new_category)
    await cb.message.answer(t(lang, "cat.ask_name"))


@router.message(SettingsFlow.new_category, F.text, ~F.text.startswith("/"))
async def newcat_name(message: Message, state: FSMContext, lang: str) -> None:
    await _ask_bucket_for_category(message, state, lang, message.text)


async def _ask_bucket_for_category(message: Message, state: FSMContext, lang: str, raw: str) -> None:
    name, emoji = _split_emoji(raw)
    if not name:
        await message.answer(t(lang, "cat.ask_name"))
        return
    await state.set_state(SettingsFlow.new_category)
    await state.update_data(cat_name=name[:40], cat_emoji=emoji)
    from ..i18n import bucket_name
    await message.answer(
        t(lang, "cat.ask_bucket", emoji=emoji, name=esc(name)),
        reply_markup=kb([[(bucket_name(lang, b), f"nc_b:{b}") for b in config.BUCKETS]]))


@router.callback_query(F.data.startswith("nc_b:"))
async def newcat_bucket(cb: CallbackQuery, state: FSMContext, db, user, lang: str) -> None:
    bucket = cb.data.split(":", 1)[1]
    data = await state.get_data()
    await cb.answer()
    if bucket not in config.BUCKETS or not data.get("cat_name"):
        return
    service.add_category(db, user["telegram_id"], data["cat_name"], data.get("cat_emoji", "🏷"), bucket)
    await state.clear()
    await safe_edit(cb.message, t(lang, "cat.created", emoji=data.get("cat_emoji", "🏷"), name=esc(data["cat_name"])))


# ---------------------------------------------------------------------- delete data
@router.message(Command("deletedata"))
async def cmd_deletedata(message: Message, lang: str) -> None:
    await message.answer(
        t(lang, "del.warn"),
        reply_markup=kb([[(t(lang, "del.yes"), "del:yes"), (t(lang, "btn.cancel"), "del:no")]]))


@router.callback_query(F.data.startswith("del:"))
async def on_delete_data(cb: CallbackQuery, state: FSMContext, db, user, lang: str) -> None:
    await cb.answer()
    if cb.data.endswith(":yes"):
        service.delete_user_data(db, user["telegram_id"])
        await state.clear()
        await safe_edit(cb.message, t(lang, "del.done"))
    else:
        await safe_edit(cb.message, t(lang, "cancelled"))


# -------------------------------------------------------------------------- admin
@router.message(Command("admin"))
async def cmd_admin(message: Message, db) -> None:
    """Usage numbers for the bot owner. Silent for everyone who is not listed in ADMIN_IDS."""
    if message.from_user.id not in config.ADMIN_IDS:
        return
    users = db.scalar("SELECT COUNT(*) FROM users", default=0)
    onboarded = db.scalar("SELECT COUNT(*) FROM users WHERE onboarded = 1", default=0)
    active = db.scalar(
        "SELECT COUNT(DISTINCT user_id) FROM expenses WHERE created_at >= datetime('now', '-7 days')", default=0)
    expenses = db.scalar("SELECT COUNT(*) FROM expenses", default=0)
    by_lang = ", ".join(f"{r['language']}: {r['n']}" for r in db.query(
        "SELECT language, COUNT(*) AS n FROM users GROUP BY language ORDER BY n DESC"))
    await message.answer(
        f"👑 <b>Admin</b>\nUsers: {users} (finished setup: {onboarded})\n"
        f"Active in the last 7 days: {active}\nExpenses logged: {expenses}\nLanguages: {by_lang or '-'}")
