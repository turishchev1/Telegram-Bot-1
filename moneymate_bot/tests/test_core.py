"""Tests for everything that does not need Telegram. Run from the project folder:

    python -m unittest discover -s tests -v
"""
import io
import json
import random
import string
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import charts, config, due, exports, service, stats, tips  # noqa: E402
from app.categories import guess_default_category  # noqa: E402
from app.db import Database  # noqa: E402
from app.i18n import t  # noqa: E402
from app.parser import parse_message  # noqa: E402
from app.period import parse_period  # noqa: E402
from app.utils import format_money, parse_hhmm, parse_percent_list  # noqa: E402

TODAY = date(2026, 11, 16)


class ParserTests(unittest.TestCase):
    def parse(self, text):
        return parse_message(text, TODAY)

    def test_simple_expense(self):
        p = self.parse("coffee 15000")
        self.assertEqual((p.amount, p.note, p.is_income, p.date), (15000, "coffee", False, None))

    def test_suffixes(self):
        self.assertEqual(self.parse("taxi 22k").amount, 22000)
        self.assertEqual(self.parse("1.5m rent").amount, 1_500_000)
        self.assertEqual(self.parse("такси 30 тыс").amount, 30000)
        self.assertEqual(self.parse("taksi 20 ming").amount, 20000)

    def test_grouped_numbers(self):
        self.assertEqual(self.parse("15 000 такси").amount, 15000)
        self.assertEqual(self.parse("15,000 lunch").amount, 15000)
        self.assertEqual(self.parse("1.500 bread").amount, 1500)

    def test_bare_number(self):
        p = self.parse("15000")
        self.assertEqual((p.amount, p.note), (15000, ""))

    def test_dates(self):
        self.assertEqual(self.parse("taxi 22k yesterday").date, date(2026, 11, 15))
        self.assertEqual(self.parse("taksi 20 ming kecha").date, date(2026, 11, 15))
        self.assertEqual(self.parse("food 100000 позавчера").date, date(2026, 11, 14))
        self.assertEqual(self.parse("такси 12.11 30 тыс").date, date(2026, 11, 12))
        self.assertEqual(self.parse("gift 30.10.2026 200k").date, date(2026, 10, 30))
        self.assertEqual(self.parse("lunch 2026-11-10 50000").date, date(2026, 11, 10))

    def test_future_day_month_means_last_year(self):
        self.assertEqual(self.parse("lunch 5000 20.12").date, date(2025, 12, 20))

    def test_income(self):
        self.assertTrue(self.parse("+1000 salary").is_income)
        self.assertTrue(self.parse("зарплата 5 000 000").is_income)
        self.assertTrue(self.parse("maosh 3000000").is_income)
        self.assertFalse(self.parse("coffee 15000").is_income)

    def test_largest_number_is_amount(self):
        p = self.parse("3 coffees 45000")
        self.assertEqual(p.amount, 45000)
        self.assertEqual(p.note, "3 coffees")

    def test_currency_words_removed(self):
        p = self.parse("bozor 120 000 so'm")
        self.assertEqual((p.amount, p.note), (120000, "bozor"))

    def test_no_amount(self):
        self.assertIsNone(self.parse("hello").amount)


class CategoryTests(unittest.TestCase):
    def test_three_languages_agree(self):
        for words in (("taxi", "такси", "taksi"), ("coffee", "кофе", "qahva"), ("groceries", "продукты", "bozor"),
                      ("rent", "аренда", "ijara"), ("pharmacy", "аптека", "dorixona")):
            guesses = {guess_default_category(w) for w in words}
            self.assertEqual(len(guesses), 1, words)
            self.assertNotIn(None, guesses)

    def test_unknown(self):
        self.assertIsNone(guess_default_category("qwertyuiop"))
        self.assertIsNone(guess_default_category(""))


class MoneyTests(unittest.TestCase):
    def test_format(self):
        self.assertEqual(format_money(15000, "UZS"), "15 000 UZS")
        self.assertEqual(format_money(1234.5, "USD"), "$1,234.50")
        self.assertEqual(format_money(-250000, "UZS"), "-250 000 UZS")

    def test_split_amounts(self):
        self.assertEqual(service.split_amounts(1000, (80, 10, 10)), [800, 100, 100])
        shares = service.split_amounts(100.01, (33.3, 33.3, 33.4))
        self.assertAlmostEqual(sum(shares), 100.01, places=2)
        with self.assertRaises(ValueError):
            service.split_amounts(1000, (50, 30, 30))

    def test_helpers(self):
        self.assertEqual(parse_hhmm("9"), "09:00")
        self.assertEqual(parse_hhmm("21:30"), "21:30")
        self.assertEqual(parse_hhmm("2130"), "21:30")
        self.assertIsNone(parse_hhmm("25:00"))
        self.assertEqual(parse_percent_list("80/10/10"), [80, 10, 10])
        self.assertEqual(parse_percent_list("80 10%"), [80, 10])
        self.assertIsNone(parse_percent_list("abc"))


class PeriodTests(unittest.TestCase):
    def test_periods(self):
        p, rest = parse_period(["food", "last", "month"], TODAY)
        self.assertEqual((p.start, p.end, rest), (date(2026, 10, 1), date(2026, 10, 31), ["food"]))
        p, _ = parse_period(["october"], TODAY)
        self.assertEqual(p.start, date(2026, 10, 1))
        p, _ = parse_period(["октябрь"], TODAY)
        self.assertEqual(p.start, date(2026, 10, 1))
        p, _ = parse_period(["dekabr"], TODAY)  # December has not happened yet this year
        self.assertEqual(p.start, date(2025, 12, 1))
        p, rest = parse_period(["transport"], TODAY)
        self.assertIsNone(p)
        self.assertEqual(rest, ["transport"])
        p, _ = parse_period(["week"], TODAY)
        self.assertEqual((p.start, p.end), (date(2026, 11, 16), TODAY))  # TODAY is a Monday


class DatabaseCase(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.user = service.get_or_create_user(self.db, 111, "Ali", "en")
        self.tid = 111
        self.addCleanup(self.db.close)

    def cat(self, key):
        return service.category_by_key(self.db, self.tid, key)["id"]

    def add(self, amount, key, day, note=""):
        return service.add_expense(self.db, self.tid, amount, self.cat(key), note, day)


class ServiceTests(DatabaseCase):
    def test_user_defaults_and_categories(self):
        self.assertEqual(self.user["language"], "en")
        self.assertEqual(len(service.list_categories(self.db, self.tid)), 13)
        self.assertEqual(service.get_split(self.user), (50, 30, 20))

    def test_expense_takes_bucket_from_category(self):
        eid = self.add(22000, "transport", TODAY)
        self.assertEqual(service.get_expense(self.db, self.tid, eid)["bucket"], "needs")
        eid = self.add(15000, "food", TODAY)
        self.assertEqual(service.get_expense(self.db, self.tid, eid)["bucket"], "wants")

    def test_resolve_category(self):
        self.assertEqual(service.resolve_category(self.db, self.tid, "taxi")["key"], "transport")
        self.assertIsNone(service.resolve_category(self.db, self.tid, "zzzz"))
        service.add_category(self.db, self.tid, "Pets", "🐶", "needs")
        self.assertEqual(service.resolve_category(self.db, self.tid, "pets food")["name"], "Pets")

    def test_other_users_data_is_separate(self):
        service.get_or_create_user(self.db, 222, "Bo", "ru")
        eid = self.add(5000, "food", TODAY)
        self.assertIsNone(service.get_expense(self.db, 222, eid))
        self.assertFalse(service.delete_expense(self.db, 222, eid))
        self.assertTrue(service.delete_expense(self.db, self.tid, eid))

    def test_query_filters_and_paging(self):
        for i in range(25):
            self.add(1000 * (i + 1), "transport", TODAY - timedelta(days=i % 5), f"ride {i}")
        self.add(999, "food", TODAY, "pizza")
        rows, total, n = service.query_expenses(self.db, self.tid, category_id=self.cat("transport"), limit=10)
        self.assertEqual((len(rows), n, total), (10, 25, sum(1000 * (i + 1) for i in range(25))))
        rows2, _, _ = service.query_expenses(self.db, self.tid, category_id=self.cat("transport"), limit=10, offset=20)
        self.assertEqual(len(rows2), 5)
        rows, _, n = service.query_expenses(self.db, self.tid, min_amount=20000)
        self.assertEqual(n, 6)
        rows, _, n = service.query_expenses(self.db, self.tid, text="PIZZA")
        self.assertEqual(n, 1)
        rows, _, _ = service.query_expenses(self.db, self.tid, limit=3, order="amount")
        self.assertEqual([r["amount"] for r in rows], [25000, 24000, 23000])

    def test_income_split_and_balances(self):
        service.add_income(self.db, self.tid, 1000, "salary", TODAY, (80, 10, 10))
        self.add(300, "bills", TODAY)   # needs
        self.add(40, "fun", TODAY)      # wants
        first, last = date(2026, 11, 1), date(2026, 11, 30)
        bal = service.bucket_balances(self.db, self.tid, first, last)
        self.assertEqual(bal["needs"]["allocated"], 800)
        self.assertEqual(bal["needs"]["left"], 500)
        self.assertEqual(bal["wants"]["left"], 60)
        self.assertEqual(bal["savings"]["left"], 100)

    def test_unspent_money_rolls_over(self):
        service.add_income(self.db, self.tid, 1000, "salary", date(2026, 10, 5), (50, 30, 20))
        self.add(100, "bills", date(2026, 10, 6))
        bal = service.bucket_balances(self.db, self.tid, date(2026, 11, 1), date(2026, 11, 30))
        self.assertEqual(bal["needs"]["left"], 400)
        self.assertEqual(bal["needs"]["month_spent"], 0)

    def test_bad_split_rejected_and_nothing_saved(self):
        with self.assertRaises(ValueError):
            service.add_income(self.db, self.tid, 1000, "x", TODAY, (60, 30, 30))
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM incomes"), 0)

    def test_delete_income_removes_allocations(self):
        iid = service.add_income(self.db, self.tid, 1000, "x", TODAY, (50, 30, 20))
        self.assertTrue(service.delete_income(self.db, self.tid, iid))
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM allocations"), 0)

    def test_delete_user_data_cascades(self):
        service.save_profile(self.db, self.tid, age=21, is_student=1)
        self.add(1000, "food", TODAY)
        service.add_income(self.db, self.tid, 1000, "x", TODAY, (50, 30, 20))
        service.delete_user_data(self.db, self.tid)
        for table in ("users", "profiles", "categories", "expenses", "incomes", "allocations"):
            self.assertEqual(self.db.scalar(f"SELECT COUNT(*) FROM {table}"), 0, table)

    def test_profile(self):
        service.save_profile(self.db, self.tid, age=21)
        service.save_profile(self.db, self.tid, occupation="student", is_student=1)
        p = service.get_profile(self.db, self.tid)
        self.assertEqual((p["age"], p["occupation"], p["is_student"]), (21, "student", 1))
        with self.assertRaises(ValueError):
            service.save_profile(self.db, self.tid, bogus=1)


class StatsTests(DatabaseCase):
    def seed(self):
        """Six months of data where December 2025 is by far the priciest."""
        random.seed(1)
        for months_back, base in ((5, 200_000), (4, 250_000), (3, 900_000), (2, 300_000), (1, 350_000), (0, 120_000)):
            first = date(2026, 11 - months_back, 1) if months_back <= 10 else None
            for i in range(10):
                self.add(base / 10, random.choice(["food", "transport", "shopping"]), first + timedelta(days=i * 2))

    def test_monthly_totals(self):
        self.seed()
        data = stats.monthly_totals(self.db, self.tid, 6, TODAY)
        self.assertEqual(len(data), 6)
        self.assertEqual(max(data, key=lambda x: x[1])[0], date(2026, 8, 1))

    def test_insights_name_the_top_month(self):
        self.seed()
        lines = stats.insight_lines(self.db, self.user, TODAY)
        text = "\n".join(lines)
        self.assertIn("August 2026", text)
        self.assertTrue(len(lines) >= 4)

    def test_insights_empty_when_no_data(self):
        self.assertEqual(stats.insight_lines(self.db, self.user, TODAY), [])

    def test_insights_in_all_languages(self):
        self.seed()
        for lang in ("ru", "uz"):
            service.update_user(self.db, self.tid, language=lang)
            lines = stats.insight_lines(self.db, service.get_user(self.db, self.tid), TODAY)
            self.assertTrue(lines)
            for line in lines:
                self.assertNotRegex(line, r"\{[a-z_]+\}")


class OutputTests(DatabaseCase):
    def setUp(self):
        super().setUp()
        service.add_income(self.db, self.tid, 5_000_000, "salary", date(2026, 11, 1), (50, 30, 20))
        for i, key in enumerate(["food", "transport", "groceries", "fun", "bills"] * 4):
            service.add_expense(self.db, self.tid, 20000 + i * 1000, self.cat(key), f"note {i}", date(2026, 11, 1 + i % 15))

    def test_charts_are_png(self):
        for lang in ("en", "ru", "uz"):
            service.update_user(self.db, self.tid, language=lang)
            user = service.get_user(self.db, self.tid)
            for png in (charts.monthly_chart(self.db, user, TODAY),
                        charts.category_chart(self.db, user, date(2026, 11, 1), date(2026, 11, 30)),
                        charts.weekday_chart(self.db, user, TODAY)):
                self.assertTrue(png.startswith(b"\x89PNG"))
                self.assertGreater(len(png), 5000)

    def test_excel_workbook(self):
        from openpyxl import load_workbook
        for lang in ("en", "ru", "uz"):
            service.update_user(self.db, self.tid, language=lang)
            user = service.get_user(self.db, self.tid)
            data = exports.build_workbook(self.db, user, date(2026, 11, 1), date(2026, 11, 30))
            wb = load_workbook(io.BytesIO(data))
            self.assertEqual(len(wb.sheetnames), 3)
            expenses = wb[t(lang, "xl.expenses")]
            self.assertEqual(expenses.max_row, 21)  # header + 20 entries
            income = wb[t(lang, "xl.income")]
            self.assertEqual(income["C2"].value, 5_000_000)
            self.assertEqual(income["D2"].value, 2_500_000)
            self.assertEqual(len(wb[t(lang, "xl.summary")]._charts), 2)

    def test_excel_with_no_data(self):
        from openpyxl import load_workbook
        user = service.get_user(self.db, self.tid)
        data = exports.build_workbook(self.db, user, date(2020, 1, 1), date(2020, 1, 31))
        self.assertEqual(len(load_workbook(io.BytesIO(data)).sheetnames), 3)


class DueTests(DatabaseCase):
    def utc(self, y, m, d, h, mi=0):
        return datetime(y, m, d, h, mi, tzinfo=timezone.utc)

    def test_tip_goes_out_once_per_local_day(self):
        service.update_user(self.db, self.tid, onboarded=1, tip_time="09:00")  # Tashkent = UTC+5
        self.assertEqual(due.users_due_for_tip(self.db, self.utc(2026, 11, 16, 3, 59)), [])    # 08:59 local
        self.assertEqual(len(due.users_due_for_tip(self.db, self.utc(2026, 11, 16, 4, 0))), 1)  # 09:00 local
        service.update_user(self.db, self.tid, last_tip_date="2026-11-16")
        self.assertEqual(due.users_due_for_tip(self.db, self.utc(2026, 11, 16, 12, 0)), [])
        self.assertEqual(len(due.users_due_for_tip(self.db, self.utc(2026, 11, 17, 5, 0))), 1)

    def test_tips_respect_other_timezones_and_switch(self):
        service.update_user(self.db, self.tid, onboarded=1, tip_time="09:00", timezone="Europe/London")
        self.assertEqual(due.users_due_for_tip(self.db, self.utc(2026, 11, 16, 8, 59)), [])
        self.assertEqual(len(due.users_due_for_tip(self.db, self.utc(2026, 11, 16, 9, 0))), 1)
        service.update_user(self.db, self.tid, tips_enabled=0)
        self.assertEqual(due.users_due_for_tip(self.db, self.utc(2026, 11, 16, 9, 0)), [])

    def test_not_onboarded_gets_nothing(self):
        self.assertEqual(due.users_due_for_tip(self.db, self.utc(2026, 11, 16, 12)), [])
        self.assertEqual(due.users_due_for_report(self.db, self.utc(2026, 11, 2, 12)), [])

    def test_monthly_report_window(self):
        service.update_user(self.db, self.tid, onboarded=1)
        self.assertEqual(due.users_due_for_report(self.db, self.utc(2026, 11, 1, 3)), [])  # 08:00 local on the 1st
        got = due.users_due_for_report(self.db, self.utc(2026, 11, 1, 4))                    # 09:00 local
        self.assertEqual(len(got), 1)
        _, first, last = got[0]
        self.assertEqual((first, last), (date(2026, 10, 1), date(2026, 10, 31)))
        self.assertEqual(len(due.users_due_for_report(self.db, self.utc(2026, 11, 5, 12))), 1)  # late catch-up
        self.assertEqual(due.users_due_for_report(self.db, self.utc(2026, 11, 20, 12)), [])     # too late
        service.update_user(self.db, self.tid, last_report_month="2026-10")
        self.assertEqual(due.users_due_for_report(self.db, self.utc(2026, 11, 5, 12)), [])      # already sent

    def test_january_report_covers_december(self):
        service.update_user(self.db, self.tid, onboarded=1)
        _, first, last = due.users_due_for_report(self.db, self.utc(2027, 1, 2, 12))[0]
        self.assertEqual((first, last), (date(2026, 12, 1), date(2026, 12, 31)))

    def test_reminder(self):
        service.update_user(self.db, self.tid, onboarded=1, reminders_enabled=1)
        self.assertEqual(due.users_due_for_reminder(self.db, self.utc(2026, 11, 16, 14)), [])   # 19:00 local
        self.assertEqual(len(due.users_due_for_reminder(self.db, self.utc(2026, 11, 16, 15))), 1)
        self.add_today()
        self.assertEqual(due.users_due_for_reminder(self.db, self.utc(2026, 11, 16, 15)), [])

    def add_today(self):
        service.add_expense(self.db, self.tid, 100, None, "x", date(2026, 11, 16))


class TipTests(DatabaseCase):
    def test_tip_bank_is_complete(self):
        bank = tips.load_tips()
        self.assertGreaterEqual(len(bank), 30)
        for tip in bank:
            for lang in config.LANGUAGES:
                self.assertTrue(tip.get(lang, "").strip(), (tip["id"], lang))

    def test_no_repeats_until_all_seen(self):
        seen = set()
        rng = random.Random(7)
        for _ in range(len(tips.load_tips())):
            tip = tips.pick_tip(self.db, self.user, TODAY, rng)
            self.assertNotIn(tip["id"], seen)
            seen.add(tip["id"])
            tips.mark_sent(self.db, self.tid, tip["id"])
        again = tips.pick_tip(self.db, self.user, TODAY, rng)  # all seen: starts over
        self.assertIsNotNone(again)

    def test_debt_tips_for_people_with_debt(self):
        service.save_profile(self.db, self.tid, debt_total=5_000_000)
        self.assertIn("debt", tips.contextual_tags(self.db, self.user, TODAY))


class LocaleTests(unittest.TestCase):
    def test_same_keys_and_placeholders(self):
        locales = {}
        for lang in config.LANGUAGES:
            locales[lang] = json.loads((Path(__file__).parent.parent / "app" / "locales" / f"{lang}.json").read_text("utf-8"))
        self.assertEqual(set(locales["en"]), set(locales["ru"]))
        self.assertEqual(set(locales["en"]), set(locales["uz"]))
        fmt = string.Formatter()
        for key in locales["en"]:
            fields = [{f for _, f, _, _ in fmt.parse(locales[l][key]) if f} for l in locales]
            self.assertEqual(fields[0], fields[1], key)
            self.assertEqual(fields[0], fields[2], key)

    def test_no_empty_strings(self):
        for lang in config.LANGUAGES:
            data = json.loads((Path(__file__).parent.parent / "app" / "locales" / f"{lang}.json").read_text("utf-8"))
            for key, value in data.items():
                self.assertTrue(value.strip(), (lang, key))

    def test_missing_key_falls_back(self):
        self.assertEqual(t("en", "does.not.exist"), "does.not.exist")


if __name__ == "__main__":
    unittest.main()
