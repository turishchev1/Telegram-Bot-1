"""PNG charts sent to Telegram.

Design: one accent hue (blue) for the thing to look at, gray for context, thin bars,
hairline grid, direct value labels on the marks that matter. No legend is needed because each
chart shows a single measure. Text uses neutral ink, never the series colour.
"""
from __future__ import annotations

import io
from datetime import date

import matplotlib

matplotlib.use("Agg")  # no display needed on a server
import matplotlib.pyplot as plt  # noqa: E402

from .i18n import category_name, month_short, t, weekday_short  # noqa: E402
from .stats import category_totals, monthly_totals, weekday_totals  # noqa: E402
from .utils import month_bounds  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
ACCENT = "#2a78d6"
CONTEXT = "#c3c2b7"
SEQ_LIGHT = "#86b6ef"  # blue ramp step 250, used for the "rest" bars in ranked charts

plt.rcParams.update({
    "font.family": "DejaVu Sans",  # has Latin and Cyrillic glyphs
    "axes.unicode_minus": False,
})


def compact(x: float) -> str:
    """15000 -> '15k', 1_250_000 -> '1.25M'."""
    ax = abs(x)
    if ax >= 1_000_000:
        v = x / 1_000_000
        return f"{v:.2f}".rstrip("0").rstrip(".") + "M"
    if ax >= 1_000:
        v = x / 1_000
        return f"{v:.1f}".rstrip("0").rstrip(".") + "k"
    return f"{x:.0f}" if x == int(x) else f"{x:.1f}"


def _base_axes(width=8.0, height=4.6):
    fig, ax = plt.subplots(figsize=(width, height), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.tick_params(axis="both", length=0, labelsize=9, labelcolor=INK_2)
    return fig, ax


def _title(fig, title: str, subtitle: str) -> None:
    fig.text(0.04, 0.955, title, fontsize=14, fontweight="bold", color=INK, ha="left", va="top")
    fig.text(0.04, 0.895, subtitle, fontsize=9.5, color=INK_2, ha="left", va="top")


def _to_png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=SURFACE)
    plt.close(fig)
    return buf.getvalue()


def monthly_chart(db, user, today: date, months: int = 12) -> bytes:
    """Column chart of the last `months` months; the biggest month is the accent."""
    lang, cur = user["language"], user["currency"]
    data = monthly_totals(db, user["telegram_id"], months, today)
    labels = [month_short(lang, m.month) for m, _ in data]
    values = [v for _, v in data]
    top = max(range(len(values)), key=lambda i: values[i]) if any(values) else -1

    fig, ax = _base_axes()
    fig.subplots_adjust(left=0.10, right=0.97, top=0.80, bottom=0.12)
    colors = [ACCENT if i == top else CONTEXT for i in range(len(values))]
    ax.bar(range(len(values)), values, width=0.55, color=colors, edgecolor=SURFACE, linewidth=0)
    ax.set_xticks(range(len(values)))
    ax.set_xticklabels(labels)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: compact(v)))
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ymax = max(values) if any(values) else 1
    ax.set_ylim(0, ymax * 1.18)
    for i in {top, len(values) - 1}:
        if i >= 0 and values[i] > 0:
            ax.text(i, values[i] + ymax * 0.02, compact(values[i]), ha="center", va="bottom",
                    fontsize=9, color=INK, fontweight="bold" if i == top else "normal")
    _title(fig, t(lang, "chart.monthly_title"),
           t(lang, "chart.monthly_sub", currency=cur,
             month=month_short(lang, data[top][0].month) if top >= 0 else "-"))
    return _to_png(fig)


def category_chart(db, user, start: date, end: date, top_n: int = 8) -> bytes:
    """Ranked horizontal bars, largest first. The biggest category is the accent."""
    lang, cur = user["language"], user["currency"]
    rows = category_totals(db, user["telegram_id"], start, end)
    total = sum(r["total"] for r in rows) or 1
    shown = rows[:top_n]
    rest = sum(r["total"] for r in rows[top_n:])
    names = [category_name(r if r["id"] else None, lang) for r in shown]
    values = [r["total"] for r in shown]
    if rest > 0:
        names.append(t(lang, "chart.other_rest"))
        values.append(rest)

    n = max(len(values), 1)
    fig, ax = _base_axes(height=1.5 + 0.48 * n)
    fig.subplots_adjust(left=0.24, right=0.80, top=1 - 1.05 / (1.5 + 0.48 * n), bottom=0.06)
    ypos = list(range(len(values)))[::-1]
    colors = [ACCENT if i == 0 else SEQ_LIGHT for i in range(len(values))]
    ax.barh(ypos, values, height=0.55, color=colors, edgecolor=SURFACE, linewidth=0)
    ax.set_yticks(ypos)
    ax.set_yticklabels(names)
    ax.set_xticks([])
    ax.spines["bottom"].set_visible(False)
    ax.set_xlim(0, (max(values) if values else 1) * 1.02)
    for y, v in zip(ypos, values):
        ax.text(v + (max(values) * 0.02 if values else 0), y, f"{compact(v)} · {v / total * 100:.0f}%",
                va="center", ha="left", fontsize=9, color=INK)
    sub = f"{start.strftime('%d.%m.%Y')} – {end.strftime('%d.%m.%Y')} · {cur}"
    _title(fig, t(lang, "chart.category_title"), sub)
    return _to_png(fig)


def weekday_chart(db, user, today: date, days: int = 90) -> bytes:
    """Spending per weekday over the last `days` days; the priciest weekday is the accent."""
    from datetime import timedelta
    lang, cur = user["language"], user["currency"]
    data = weekday_totals(db, user["telegram_id"], today - timedelta(days=days), today)
    values = [s for s, _ in data]
    top = max(range(7), key=lambda i: values[i]) if any(values) else -1

    fig, ax = _base_axes(height=4.2)
    fig.subplots_adjust(left=0.10, right=0.97, top=0.78, bottom=0.12)
    ax.bar(range(7), values, width=0.55, color=[ACCENT if i == top else CONTEXT for i in range(7)],
           edgecolor=SURFACE, linewidth=0)
    ax.set_xticks(range(7))
    ax.set_xticklabels([weekday_short(lang, i) for i in range(7)])
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: compact(v)))
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ymax = max(values) if any(values) else 1
    ax.set_ylim(0, ymax * 1.18)
    if top >= 0:
        ax.text(top, values[top] + ymax * 0.02, compact(values[top]), ha="center", va="bottom",
                fontsize=9, color=INK, fontweight="bold")
    _title(fig, t(lang, "chart.weekday_title"), t(lang, "chart.weekday_sub", days=days, currency=cur))
    return _to_png(fig)
