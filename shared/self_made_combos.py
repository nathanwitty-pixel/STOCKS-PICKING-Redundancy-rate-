"""self_made_combos.py — the parts of the Marketing dashboard's self_made_combos.py that Stocks Picking uses, copied
word for word (refresh with sync_from_dashboard.py): the per-day bag sales SQL for each market and the bag resolver
(bag_classifier, on bag_original_prices.json). Everything else of that page is not needed here."""
import json
import os
import re

_BAG_PRICES = None


def _load_bag_prices():
    """{BAG_UPPER: original full price} from bag_original_prices.json — the baseline the
    combo monetary-implication measures the bundling discount against. Editable there."""
    global _BAG_PRICES
    if _BAG_PRICES is not None:
        return _BAG_PRICES
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bag_original_prices.json")
    out = {}
    try:
        for k, v in json.load(open(path, encoding="utf-8")).items():
            if str(k).startswith("_"):
                continue
            try:
                out[str(k).strip().upper()] = int(v)
            except (ValueError, TypeError):
                pass
    except Exception:                                        # noqa: BLE001
        out = {}
    _BAG_PRICES = out
    return out


def _bag_sales_daily_sql(market_sql):
    """Per-day bag sales (units only) for a market — same product filters as _bag_sales_sql,
    plus a date column, so the "not on offer" cover-days metric can use the number of days a
    bag ACTUALLY sold instead of calendar days elapsed."""
    return f"""
SELECT p.date_order::date AS d, UPPER(pt."name") AS name, SUM(pl.qty)::int AS units
FROM pos_order p JOIN pos_order_line pl ON pl.order_id=p.id
LEFT JOIN pos_session ps ON p.session_id=ps.id
LEFT JOIN pos_config pc ON ps.config_id=pc.id
LEFT JOIN product_product pp ON pl.product_id=pp.id
LEFT JOIN product_template pt ON pp.product_tmpl_id=pt.id
WHERE p.date_order::date BETWEEN :s AND :e AND p.state IN ('done', 'invoiced', 'paid') AND pl.qty <> 0 AND NOT COALESCE(pl.sub_product_line, false)
  {market_sql}
  AND pt."name" NOT LIKE '%+%'
  AND pt."name" NOT ILIKE '%delivery%' AND pt."name" NOT ILIKE '%customi%'
  AND pt."name" NOT ILIKE '%strap%' AND pt."name" NOT ILIKE 'gift bag%'
GROUP BY 1, 2
"""

BAG_SALES_DAILY_SQL        = _bag_sales_daily_sql("AND lower(COALESCE(pc.\"name\",'')) NOT IN ('sinza','dar-es-alam','uganda')")
BAG_SALES_DAILY_SINZA_SQL  = _bag_sales_daily_sql("AND lower(COALESCE(pc.\"name\",'')) IN ('sinza','dar-es-alam')")
BAG_SALES_DAILY_UGANDA_SQL = _bag_sales_daily_sql("AND lower(COALESCE(pc.\"name\",'')) = 'uganda'")


def bag_classifier(on_offer_raw):
    """(infer, is_on_offer) for a market's on-offer bag names — shared by the "Bags not on
    offer" panels here and the Bags on vs not on offer menu (bags_on_offer.py), so both
    resolve and classify a sold product identically.

    `infer(name)` resolves an Odoo product to its catalogue bag type (bag_original_prices.json
    keys, longest-prefix, promo aliases applied) or None. `is_on_offer(bag)` is True when the
    bag equals, or is a word-prefix either way of, any on-offer name (so an "AVANA" deal
    covers "AVANA HB")."""
    keys = sorted(_load_bag_prices().keys(), key=len, reverse=True)
    # Promo wording ↔ catalogue bag (e.g. a "Cairo backpack" deal is the CAIRO BP bag).
    _ALIAS = {"CAIRO BACKPACK": "CAIRO BP", "LAPTOP BACKPACK": "CODE 3",
              "STANDARD TRAVEL": "TRAVEL", "STANDARD": "TRAVEL", "NEO MAN BAG": "NEO MAN",
              "BRIEFCASE": "BRIEF CASE"}

    def _norm(name):
        p = re.sub(r"\s+", " ", str(name).strip().upper())
        for a, b in _ALIAS.items():
            if p == a or p.startswith(a + " "):
                return (b + p[len(a):]).strip()
        return p

    def infer(name):
        p = _norm(name)
        for k in keys:
            if p == k or p.startswith(k + " "):
                return k
        return None

    on_offer_names = {_norm(b) for b in (on_offer_raw or set()) if str(b).strip()}

    def is_on_offer(bt):
        return any(d == bt or bt.startswith(d + " ") or d.startswith(bt + " ")
                   for d in on_offer_names)

    return infer, is_on_offer
