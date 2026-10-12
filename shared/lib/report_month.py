"""lib/report_month.py — the single source of truth for "which month are we reporting?"

Every script that pulls a month of numbers must anchor on the SAME month, or the
dashboards end up labelled with one month and filled with another's figures.

That is exactly what happened on 1 Sep 2026. forward_projections.py anchors the
report month on YESTERDAY (on the 1st, the last complete day belongs to the month
just finished, so the 1st still reports that month — day 31 of 31, "August").
monthly_sales.py, new_products.py and the posting script anchored on
date.today() and so computed SEPTEMBER. The August report was built, frozen and
archived with September's day-1 numbers: 8 bags, 0.03% of target.

The rule, in one line: the reporting month is the month containing YESTERDAY.
On every day except the 1st that is identical to today's month, so this changes
nothing mid-month — it only fixes the rollover day.

Override for rebuilding a past month (e.g. regenerating August after the fact):

    $env:DENRI_REPORT_MONTH = "2026-08"     # PowerShell
    python main.py

Set it back to nothing (Remove-Item Env:DENRI_REPORT_MONTH) to return to the
automatic anchor. `is_pinned()` lets callers tell a rebuild from a normal run —
scripts that read live, point-in-time state (current stock levels, posting
counts) cannot rewind, so they use it to flag their figures as as-observed
rather than as-of-month-end.
"""
from __future__ import annotations

import calendar
import datetime
import os

ENV_VAR = "DENRI_REPORT_MONTH"


def _pinned():
    """(year, month) from DENRI_REPORT_MONTH=YYYY-MM, or None when unset/invalid."""
    raw = (os.environ.get(ENV_VAR) or "").strip()
    if not raw:
        return None
    try:
        d = datetime.datetime.strptime(raw, "%Y-%m")
    except ValueError:
        return None
    return d.year, d.month


def is_pinned() -> bool:
    """True when DENRI_REPORT_MONTH pins the month (a deliberate rebuild)."""
    return _pinned() is not None


def anchor(ref: datetime.date | None = None) -> datetime.date:
    """The date whose month is the reporting month: yesterday, unless pinned.

    Pinned runs anchor on the LAST day of the pinned month, so day-count maths
    (velocity factor, day N of M) reads as a complete month."""
    p = _pinned()
    if p:
        y, m = p
        return datetime.date(y, m, calendar.monthrange(y, m)[1])
    return (ref or datetime.date.today()) - datetime.timedelta(days=1)


def month_window(ref: datetime.date | None = None):
    """(first day, last day) of the reporting month.

    There are no future sales rows, so for an in-progress month this is
    naturally sales-to-date — same behaviour the callers had before."""
    a = anchor(ref)
    return a.replace(day=1), a.replace(day=calendar.monthrange(a.year, a.month)[1])


def live_anchor(ref: datetime.date | None = None) -> datetime.date:
    """Reporting date for the LIVE dashboard: TODAY's month, not yesterday's.

    The live Current Performance cards should always show the month we are
    actually in — on 1 Sep that is September (day 1), not the completed August.
    Only the ARCHIVED monthly report uses anchor() (yesterday) so that the 1st
    still reports the month that just finished. A pin (DENRI_REPORT_MONTH) wins
    for both, so month_end can force the exact month it is archiving."""
    p = _pinned()
    if p:
        y, m = p
        return datetime.date(y, m, calendar.monthrange(y, m)[1])
    return ref or datetime.date.today()


def live_month_window(ref: datetime.date | None = None):
    """(first day, last day) of the LIVE month (today's month, unless pinned)."""
    a = live_anchor(ref)
    return a.replace(day=1), a.replace(day=calendar.monthrange(a.year, a.month)[1])


def month_key(ref: datetime.date | None = None) -> str:
    """The reporting month as YYYY-MM — the key stored in history and Supabase."""
    return anchor(ref).strftime("%Y-%m")


def live_month_key(ref: datetime.date | None = None) -> str:
    """The LIVE month as YYYY-MM (today's month, unless pinned) — used by the live
    dashboard to match monthly_sales_db.json for the month we are actually in."""
    return live_anchor(ref).strftime("%Y-%m")


def month_name(ref: datetime.date | None = None) -> str:
    return anchor(ref).strftime("%B")
