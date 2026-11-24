"""Excel export: one workbook per period with Summary, Expenses and Income sheets."""
from __future__ import annotations

import io
from datetime import date

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import config, service
from .i18n import bucket_name, category_name, t
from .stats import bucket_totals, category_totals
from .utils import ZERO_DECIMAL_CURRENCIES

HEADER_FILL = PatternFill("solid", fgColor="2A78D6")
HEADER_FONT = Font(bold=True, color="FFFFFF")
TITLE_FONT = Font(bold=True, size=14)
BOLD = Font(bold=True)
THIN = Side(style="thin", color="E1E0D9")
ROW_BORDER = Border(bottom=THIN)


def _header(ws, row: int, labels: list[str]) -> None:
    for col, label in enumerate(labels, start=1):
        c = ws.cell(row=row, column=col, value=label)
        c.fill, c.font = HEADER_FILL, HEADER_FONT
        c.alignment = Alignment(horizontal="center", vertical="center")


def _widths(ws, widths: list[int]) -> None:
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def build_workbook(db, user, start: date, end: date) -> bytes:
    tid, lang, cur = user["telegram_id"], user["language"], user["currency"]
    money = "#,##0" if cur in ZERO_DECIMAL_CURRENCIES else "#,##0.00"
    wb = Workbook()

    expenses, total_spent, n_expenses = service.query_expenses(db, tid, start=start, end=end)
    incomes = service.list_incomes(db, tid, start, end)
    total_income = sum(float(r["amount"]) for r in incomes)

    # ---------------------------------------------------------------- Summary
    ws = wb.active
    ws.title = t(lang, "xl.summary")
    ws["A1"] = t(lang, "xl.title")
    ws["A1"].font = TITLE_FONT
    ws["A2"] = f"{start.strftime('%d.%m.%Y')} – {end.strftime('%d.%m.%Y')} · {cur}"
    rows = [
        (t(lang, "xl.total_spent"), total_spent),
        (t(lang, "xl.total_income"), total_income),
        (t(lang, "xl.net"), total_income - total_spent),
        (t(lang, "xl.n_expenses"), n_expenses),
    ]
    r = 4
    for label, value in rows:
        ws.cell(row=r, column=1, value=label).font = BOLD
        c = ws.cell(row=r, column=2, value=round(value, 2) if isinstance(value, float) else value)
        if label != rows[3][0]:
            c.number_format = money
        r += 1

    r += 1
    cat_header_row = r
    _header(ws, r, [t(lang, "xl.category"), t(lang, "xl.amount"), t(lang, "xl.share"), t(lang, "xl.count")])
    cats = category_totals(db, tid, start, end)
    for item in cats:
        r += 1
        ws.cell(row=r, column=1, value=category_name(item if item["id"] else None, lang))
        ws.cell(row=r, column=2, value=round(item["total"], 2)).number_format = money
        share = ws.cell(row=r, column=3, value=(item["total"] / total_spent) if total_spent else 0)
        share.number_format = "0%"
        ws.cell(row=r, column=4, value=item["n"])
    cat_last_row = r

    r += 2
    bucket_header_row = r
    _header(ws, r, [t(lang, "xl.bucket"), t(lang, "xl.allocated"), t(lang, "xl.spent")])
    allocated = {b: 0.0 for b in config.BUCKETS}
    for inc in incomes:
        for a in service.income_allocations(db, inc["id"]):
            allocated[a["bucket"]] = allocated.get(a["bucket"], 0.0) + float(a["amount"])
    spent = bucket_totals(db, tid, start, end)
    for b in config.BUCKETS:
        r += 1
        ws.cell(row=r, column=1, value=bucket_name(lang, b))
        ws.cell(row=r, column=2, value=round(allocated[b], 2)).number_format = money
        ws.cell(row=r, column=3, value=round(spent[b], 2)).number_format = money
    bucket_last_row = r

    if cats:
        chart = BarChart()
        chart.type = "bar"
        chart.style = 10
        chart.title = t(lang, "xl.chart_categories")
        chart.legend = None
        data = Reference(ws, min_col=2, min_row=cat_header_row, max_row=cat_last_row)
        labels = Reference(ws, min_col=1, min_row=cat_header_row + 1, max_row=cat_last_row)
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(labels)
        chart.y_axis.delete = False
        chart.x_axis.delete = False
        chart.height, chart.width = 8, 16
        ws.add_chart(chart, "F3")

    chart2 = BarChart()
    chart2.type = "col"
    chart2.style = 10
    chart2.title = t(lang, "xl.chart_buckets")
    chart2.add_data(Reference(ws, min_col=2, max_col=3, min_row=bucket_header_row, max_row=bucket_last_row),
                    titles_from_data=True)
    chart2.set_categories(Reference(ws, min_col=1, min_row=bucket_header_row + 1, max_row=bucket_last_row))
    chart2.y_axis.delete = False
    chart2.x_axis.delete = False
    chart2.height, chart2.width = 8, 16
    ws.add_chart(chart2, "F21")
    _widths(ws, [26, 18, 12, 10])

    # --------------------------------------------------------------- Expenses
    we = wb.create_sheet(t(lang, "xl.expenses"))
    _header(we, 1, [t(lang, "xl.date"), t(lang, "xl.category"), t(lang, "xl.bucket"),
                    t(lang, "xl.amount"), t(lang, "xl.note")])
    for i, e in enumerate(reversed(list(expenses)), start=2):  # oldest first in the sheet
        we.cell(row=i, column=1, value=date.fromisoformat(e["spent_on"])).number_format = "DD.MM.YYYY"
        we.cell(row=i, column=2, value=category_name(
            {"key": e["cat_key"], "name": e["cat_name"]} if e["category_id"] else None, lang))
        we.cell(row=i, column=3, value=bucket_name(lang, e["bucket"]))
        we.cell(row=i, column=4, value=float(e["amount"])).number_format = money
        we.cell(row=i, column=5, value=e["note"])
        for col in range(1, 6):
            we.cell(row=i, column=col).border = ROW_BORDER
    we.freeze_panes = "A2"
    we.auto_filter.ref = f"A1:E{max(len(expenses) + 1, 2)}"
    _widths(we, [13, 18, 14, 16, 40])

    # ----------------------------------------------------------------- Income
    wi = wb.create_sheet(t(lang, "xl.income"))
    _header(wi, 1, [t(lang, "xl.date"), t(lang, "xl.source"), t(lang, "xl.amount")]
            + [bucket_name(lang, b) for b in config.BUCKETS])
    for i, inc in enumerate(incomes, start=2):
        wi.cell(row=i, column=1, value=date.fromisoformat(inc["received_on"])).number_format = "DD.MM.YYYY"
        wi.cell(row=i, column=2, value=inc["source"])
        wi.cell(row=i, column=3, value=float(inc["amount"])).number_format = money
        by_bucket = {a["bucket"]: float(a["amount"]) for a in service.income_allocations(db, inc["id"])}
        for j, b in enumerate(config.BUCKETS, start=4):
            wi.cell(row=i, column=j, value=by_bucket.get(b, 0.0)).number_format = money
        for col in range(1, 7):
            wi.cell(row=i, column=col).border = ROW_BORDER
    wi.freeze_panes = "A2"
    _widths(wi, [13, 24, 16, 16, 16, 16])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
