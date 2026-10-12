"""lib/stock.py — live Odoo on-hand stock, per product / market / shop.

Single source for the dashboards' STOCK figures, replacing the STOCK_LEVELS
Google Sheet as the primary source (the sheet stays a fallback only, so an
unreachable DB never zeroes stock).

On-hand = SUM(stock_quant.quantity) over INTERNAL stock locations, per product
template name (upper-cased — the name already carries the colour in this Odoo,
e.g. "LOOP BP CN BLACK", so per-name == per bag+colour).

IMPORTANT — market split is by the location's TOP-LEVEL code
(`split_part(complete_name,'/',1)`) using an EXPLICIT shop-code allow-list, NOT
a "NOT IN ('DAR','UG')" exclusion. The exclusion would sweep in the bulk
warehouse / purchasing / production placeholder locations (WRKWH ~10.4M, PURCH
~1.8M, PROD, WIP …) that hold millions of bogus units — the real Kenya SHOP
on-hand is ~14k, matching the sheet's ~10k. The allow-list mirrors the shop
codes self_made_combos.py already uses.

Every function guards the DB (check_connection) and returns {} when Postgres is
unreachable, so callers fall back to the sheet.
"""
from . import db

# Kenya retail shop location codes. Deliberately EXCLUDES every non-retail
# location: the bulk warehouses / placeholders (WRKWH, PURCH, PROD, WIP, FINWH),
# the non-shop stores (VLD, CBD, CBS, MRKT, WEB, RJW, JUMIA, CORP, STF, SHT), and
# the non-Kenya markets (DAR→Sinza, UG→Uganda). Only the 16 codes below count as
# Kenya shop on-hand (~14k bags); adding any of the excluded codes reintroduces
# millions of bogus warehouse/placeholder units.
KENYA_SHOP_CODES = ("STAR", "MSA", "NAKS", "ELD", "KSM", "MERU", "THK", "HAZ",
                    "KITE", "NAN", "KAK", "HTN", "KSI", "KTDA", "BUSIA", "RONG")
SINZA_CODES  = ("DAR",)    # Dar-es-Salaam warehouse serves the Sinza region
UGANDA_CODES = ("UG",)
OUTSIDE_CODES = SINZA_CODES + UGANDA_CODES   # non-Kenya markets

_BASE = """
FROM stock_quant q
JOIN stock_location l ON l.id = q.location_id AND l.usage = 'internal'
JOIN product_product pp ON pp.id = q.product_id
JOIN product_template pt ON pt.id = pp.product_tmpl_id
"""


def _ok():
    """True only if Postgres is reachable — else callers fall back to the sheet."""
    try:
        ok, _ = db.check_connection()
        return bool(ok)
    except Exception:                                        # noqa: BLE001
        return False


def _codes_for(market):
    m = (market or "kenya").strip().lower()
    if m in ("kenya", "ke", ""):
        return KENYA_SHOP_CODES
    if m in ("sinza", "dar", "dar-es-salaam", "dar-es-alam"):
        return SINZA_CODES
    if m in ("uganda", "ug"):
        return UGANDA_CODES
    if m in ("outside", "non-kenya", "outside-kenya"):
        return OUTSIDE_CODES
    return KENYA_SHOP_CODES


def _qty(v):
    """On-hand as int; a NULL SUM (NaN in pandas — only reachable with positive_only=False) is 0."""
    try:
        return int(v) if v == v else 0          # NaN != NaN
    except (TypeError, ValueError):
        return 0


def _inlist(codes):
    return ", ".join("'" + str(c).strip().upper().replace("'", "''") + "'" for c in codes)


def odoo_stock_by_product(market="kenya", include_combos=False, positive_only=True):
    """{UPPER(product name): on-hand units} of live internal stock for a market.

    market: "kenya" (default), "sinza"/"dar", "uganda"/"ug", or "outside" (Sinza+Uganda).
    include_combos: keep '+' combo wrapper products (default drops them).
    positive_only: only products whose summed on-hand > 0 (default). Set False to
                   include products that net to 0 (so a live 0 can override the sheet).
    Returns {} if Postgres is unreachable → caller falls back to the STOCK_LEVELS sheet.
    """
    codes = _codes_for(market)
    if not codes or not _ok():
        return {}
    combo = "" if include_combos else " AND pt.\"name\" NOT LIKE '%+%'"
    having = " HAVING SUM(q.quantity) > 0" if positive_only else ""
    sql = f"""
    SELECT UPPER(pt."name") AS name, SUM(q.quantity)::int AS qty
    {_BASE}
    WHERE split_part(l.complete_name, '/', 1) IN ({_inlist(codes)}){combo}
    GROUP BY UPPER(pt."name"){having}
    """
    try:
        dfr = db.run_query(sql, {})
    except Exception:                                        # noqa: BLE001
        return {}
    if dfr is None or dfr.empty:
        return {}
    return {str(r["name"]).upper(): _qty(r["qty"]) for _, r in dfr.iterrows()}


RESTOCK_LOCATION = "CBD/Stock"   # the CBD store that restocks the shops (New Products "Restock")


def odoo_stock_at_location(complete_name=RESTOCK_LOCATION, include_combos=False):
    """{UPPER(product name): on-hand units} at ONE exact internal location (complete_name,
    e.g. "CBD/Stock") — not the whole top-level code, whose other sub-locations aren't
    restock stock. {} if Postgres is unreachable."""
    if not _ok():
        return {}
    combo = "" if include_combos else " AND pt.\"name\" NOT LIKE '%+%'"
    sql = f"""
    SELECT UPPER(pt."name") AS name, SUM(q.quantity)::int AS qty
    {_BASE}
    WHERE l.complete_name = :loc{combo}
    GROUP BY UPPER(pt."name") HAVING SUM(q.quantity) > 0
    """
    try:
        dfr = db.run_query(sql, {"loc": complete_name})
    except Exception:                                        # noqa: BLE001
        return {}
    if dfr is None or dfr.empty:
        return {}
    return {str(r["name"]).upper(): _qty(r["qty"]) for _, r in dfr.iterrows()}


def odoo_stock_by_shop_code(codes=None, include_combos=False, positive_only=True):
    """{top-level location code: {UPPER(product name): on-hand}} — live per-shop stock.

    codes: which shop/location top-codes to include (default the Kenya shops).
    Returns {} if Postgres is unreachable.
    """
    codes = tuple(codes) if codes else KENYA_SHOP_CODES
    if not codes or not _ok():
        return {}
    combo = "" if include_combos else " AND pt.\"name\" NOT LIKE '%+%'"
    having = " HAVING SUM(q.quantity) > 0" if positive_only else ""
    sql = f"""
    SELECT split_part(l.complete_name, '/', 1) AS code,
           UPPER(pt."name") AS name, SUM(q.quantity)::int AS qty
    {_BASE}
    WHERE split_part(l.complete_name, '/', 1) IN ({_inlist(codes)}){combo}
    GROUP BY code, UPPER(pt."name"){having}
    """
    try:
        dfr = db.run_query(sql, {})
    except Exception:                                        # noqa: BLE001
        return {}
    if dfr is None or dfr.empty:
        return {}
    out = {}
    for _, r in dfr.iterrows():
        out.setdefault(str(r["code"]).strip().upper(), {})[str(r["name"]).upper()] = _qty(r["qty"])
    return out
