"""Tests for colour_comparison.py's pure logic (no Odoo). Run:
    python -m pytest tests/test_colour_comparison.py -q
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # this folder (it adds the dashboard itself)

import colour_comparison as cc   # noqa: E402

END = datetime.date(2026, 10, 11)


def _infer(name):
    for k in ("ANTITHEFT", "CODE 3"):
        if name == k or name.startswith(k + " "):
            return k
    return None


RESOLVE = cc.make_resolver(_infer, {"LAFEMME BLACK (OBSIDIAN)": "HANDBAG", "ANTITHEFT BLACK": "BACKPACK"},
                           {"CODE 3": "BACKPACK"})


def test_fallback_bag_drops_colour_words():
    assert cc.fallback_bag("LAFEMME WINE RED (MULBERRY)") == "LAFEMME"
    assert cc.fallback_bag("LAFEMME BLACK (OBSIDIAN)") == "LAFEMME"


def test_resolver_bag_colour_category():
    assert RESOLVE("ANTITHEFT BLACK") == ("BACKPACK", "ANTITHEFT", "Black")
    assert RESOLVE("CODE 3 NUDE") == ("BACKPACK", "CODE 3", "Beige")          # Nude folds into Beige
    assert RESOLVE("LAFEMME PINK (ÉCLAT)")[1] == "LAFEMME"                    # new colour of a listed new bag


def test_resolver_leaves_out_rejects_gift_bags_and_non_bags():
    assert RESOLVE("ANTITHEFT BLACK [REJECT]") is None
    assert RESOLVE("GIFT BAG A4") is None
    assert RESOLVE("ANTIBACTERIAL WIPES") is None


def test_bucket_periods():
    daily = {"X": {"2026-10-11": 1, "2026-10-05": 2, "2026-10-01": 4, "2026-09-20": 8, "2026-09-01": 16}}
    b = cc.bucket(daily, END, datetime.date(2026, 10, 1))["X"]
    assert b == {"d7": 3, "d28": 15, "mtd": 7}


def test_rollup_folds_shades_and_counts_unmatched():
    sold = {"CODE 3 BROWN": {"d7": 1, "d28": 4, "mtd": 2}, "CODE 3 ANTELOPE BROWN": {"d7": 0, "d28": 2, "mtd": 1},
            "ANTIBACTERIAL WIPES": {"d7": 5, "d28": 9, "mtd": 6}}
    stock = {"CODE 3 BROWN": 10, "CODE 3 ANTELOPE BROWN": 3, "ANTIBACTERIAL WIPES": 100, "ANTITHEFT GREY": 0}
    rows, miss = cc.rollup(sold, stock, RESOLVE)
    assert len(rows) == 1                                   # ANTITHEFT GREY: no stock, no sales → dropped
    r = rows[0]
    assert (r["bag"], r["col"], r["stock"], r["d28"], r["mtd"]) == ("CODE 3", "Brown", 13, 6, 3)
    assert miss == {"stock": 100, "d7": 5, "d28": 9, "mtd": 6}


# ── Stock rate ─────────────────────────────────────────────────────────────

def test_daily_series_indexes_from_day0_and_drops_zeros_and_older_days():
    d0 = datetime.date(2026, 10, 1)
    out = cc.daily_series({"X": {"2026-10-04": 3, "2026-09-30": 9}}, {"X": {"2026-10-05": -2.0, "2026-10-06": 0}},
                          {"X": {"2026-10-05": 4.0}}, d0)
    assert out == {"X": {"s": {3: 3}, "n": {4: -2}, "r": {4: 4}}}


def test_rollup_sums_daily_series_per_colour():
    daily = {"CODE 3 BROWN": {"s": {1: 2}, "n": {1: -2, 2: 5}, "r": {2: 5}},
             "CODE 3 ANTELOPE BROWN": {"s": {1: 1}, "n": {1: -1}, "r": {}}}
    rows, _ = cc.rollup({}, {"CODE 3 BROWN": 10, "CODE 3 ANTELOPE BROWN": 3}, RESOLVE, daily)
    r = rows[0]
    assert (r["s"], r["n"], r["r"]) == ({"1": 3}, {"1": -3, "2": 5}, {"2": 5})
    # Stock at the start of day 1 = stock now − net moves from day 1 on: 13 − (−3 + 5) = 11 → sold 3 of 11.


def test_rollup_keeps_colour_with_only_older_sales():
    rows, _ = cc.rollup({}, {}, RESOLVE, {"ANTITHEFT GREY": {"s": {0: 2}, "n": {0: -2}, "r": {}}})
    assert [(r["bag"], r["col"], r["stock"], r["d28"]) for r in rows] == [("ANTITHEFT", "Grey", 0, 0)]


def test_periods_match_the_dashboard():
    p = cc.periods(datetime.date(2026, 10, 12), datetime.date(2026, 10, 1), datetime.date(2026, 10, 31))   # a Monday
    assert p == {"monthly": ["2026-10-01", "2026-10-12"], "weekly": ["2026-10-11", "2026-10-12"],
                 "lastweek": ["2026-10-04", "2026-10-10"]}
    assert cc.periods(datetime.date(2026, 10, 11), datetime.date(2026, 10, 1), datetime.date(2026, 10, 31))["weekly"] \
        == ["2026-10-11", "2026-10-11"]                                                                    # Sunday


def test_offer_tags_prefix_match_order_and_new_products():
    t = cc.offer_tags(["AVANA HB", "CODE 3", "LAFEMME", "ZURI"],
                      [("Avana", ["Combo"]), ("CODE 3", ["Single offer"]), ("Code 3", ["Power Deal"])], ["LAFEMME"])
    assert t == {"AVANA HB": ["Combo"], "CODE 3": ["Power Deal", "Single offer"], "LAFEMME": ["New product"]}


def test_moves_sql_uses_market_codes():
    q = cc.moves_sql(("DAR",))
    assert "IN ('DAR')" in q and "{" not in q
