"""colour_comparison.py — STOCKS PICKING (Redundancy rate): for Kenya, Sinza and Uganda, every bag's colours
side by side — live shop stock, units sold and the redundancy rate — grouped Category → Bag → Colour like the
MARKETING_WORK_PLAN "colour comparison" sheet (spec: README.md in this folder). Also the Stock rate section:
units sold in a period ÷ the shop stock there at its start, beside today's stock and on offer / not on offer.

Its own app (own GitHub repo), built on pieces of the Marketing dashboard: the Odoo connection, lib/ (stock, colours,
db, report month, receipt combos), self_made_combos' sales queries + bag resolver, bag_names.csv / bag_tiers.csv and
the offer lists. They are read from the Marketing_dashboard folder next to this one when it is there (this PC: always
its latest files and its .env), else from the copies in shared/ (Streamlit Cloud; refresh them with
sync_from_dashboard.py). DASHBOARD_DIR overrides both.

    python colour_comparison.py        # DENRI_LAUNCHER=1 to skip the browser tab
"""
import csv
import datetime
import json
import os
import re
import sys
import webbrowser
from collections import Counter, defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
_SIBLING = os.path.join(os.path.dirname(BASE), "Marketing_dashboard")
DASHBOARD = (os.environ.get("DASHBOARD_DIR")
             or (_SIBLING if os.path.isfile(os.path.join(_SIBLING, "self_made_combos.py")) else os.path.join(BASE, "shared")))
sys.path.insert(0, DASHBOARD)
# This PC: the dashboard's .env holds the Odoo login. Load it by path, so it is found even when the build uses the
# shared/ copies (lib/db.py only looks for a .env above itself). Never overrides variables already set (Cloud secrets).
if os.path.isfile(os.path.join(_SIBLING, ".env")):
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_SIBLING, ".env"))

from lib import colours   # noqa: E402  (from the dashboard)

HTML = os.path.join(BASE, "colour_comparison.html")
MARKETS = (("kenya", "Kenya"), ("sinza", "Sinza"), ("uganda", "Uganda"))
WINDOW_DAYS = 28
PERIODS = ("d7", "d28", "mtd")
# Kenya = every Kenya SHOP: lib/stock's 16 shop codes + Machakos and Nyeri, never the Website (WEB), the CBD /
# Validation (VLD) warehouses or any other store. Sales likewise come from the shop tills only (the Website, Jumia and
# Staff POS tills are left out), so units sold and stock cover the same shops everywhere on the page.
EXTRA_KENYA_SHOPS = ("MACHA", "NYERI")
KENYA_NON_SHOP_TILLS = ("website sales", "jumia", "staff pos")
DAILY_DAYS = 120          # Stock rate: days of daily sales / stock moves shipped, so any period (incl. Custom) works in the page

# Done stock moves into / out of a market's shops, per product per day (moves between two of its shops cancel).
# rcv = in from anywhere but a customer (deliveries, transfers); a customer return counts in net only.
MOVES_SQL = """
SELECT UPPER(pt."name") AS name, m.date::date AS d,
       SUM(CASE WHEN {dst} AND NOT {src} THEN m.product_qty WHEN {src} AND NOT {dst} THEN -m.product_qty ELSE 0 END) AS net,
       SUM(CASE WHEN {dst} AND NOT {src} AND ls.usage <> 'customer' THEN m.product_qty ELSE 0 END) AS rcv
FROM stock_move m JOIN stock_location ls ON ls.id = m.location_id JOIN stock_location ld ON ld.id = m.location_dest_id
JOIN product_product pp ON pp.id = m.product_id JOIN product_template pt ON pt.id = pp.product_tmpl_id
WHERE m.state = 'done' AND m.date::date >= :s AND pt."name" NOT LIKE '%+%'
GROUP BY 1, 2
"""

# Words that are part of a colour, not of the bag ("LAFEMME WINE RED" → LAFEMME). Only used for bags that
# bag_names.csv lists but the price catalogue doesn't know yet (new bags) — see fallback_bag().
_SHADE_WORDS = {"WINE", "DARK", "LIGHT", "MINT", "NAVY", "CN", "TT", "018", "CROC", "DOTTED", "PATTERN",
                "BABY", "HOT", "SKY", "ROYAL", "OLIVE", "DUSTY"}


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "").upper().replace(".", " ")).strip()


def _bag_names():
    """{NORM product name: CATEGORY} from bag_names.csv (the sheet snapshot lib/colours reads)."""
    out = {}
    try:
        with open(os.path.join(DASHBOARD, "bag_names.csv"), encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                n = _norm(r.get("PRODUCT NAME"))
                if n and "TOTAL" not in n:
                    out[n] = _norm(r.get("CATEGORY"))
    except OSError:
        pass
    return out


def _tiers():
    """{BAG: CATEGORY} from bag_tiers.csv (the Bags on offer menu's editable table)."""
    out = {}
    try:
        with open(os.path.join(DASHBOARD, "bag_tiers.csv"), encoding="utf-8") as f:
            for r in csv.DictReader(ln for ln in f if not ln.startswith("#")):
                if r.get("BAG") and (r.get("CATEGORY") or "").strip():
                    out[_norm(r["BAG"])] = _norm(r["CATEGORY"])
    except OSError:
        pass
    return out


def fallback_bag(name):
    """Bag type of a product the catalogue doesn't know: drop "(…)" and the trailing colour words."""
    words = re.sub(r"\(.*?\)", " ", _norm(name)).split()
    while len(words) > 1 and (words[-1] in _SHADE_WORDS or colours.family(words[-1])):
        words.pop()
    return " ".join(words)


# Colours as Odoo names them ("Antelope Brown", "Spice", "Cracked Black"), not folded into families. Set False to go
# back to the families of lib/colours (Spice / Antelope → Brown, Nude → Beige …); the page's colour dots use the family either way.
RAW_COLOURS = True


def _title(s):
    """ANTELOPE BROWN -> Antelope Brown; short codes / numbers stay as they are (CN, TT, 018); "(MULBERRY)" -> "(Mulberry)"."""
    out = []
    for w in s.split():
        if any(ch.isdigit() for ch in w) or len(w.strip("()[]")) <= 2:
            out.append(w)
        else:                                                # each part of BLACK/CRACKED → Black/Cracked
            parts = []
            for part in w.split("/"):
                i = next((k for k, ch in enumerate(part) if ch.isalpha()), 0)
                parts.append(part[:i] + part[i:i + 1].upper() + part[i + 1:].lower())
            out.append("/".join(parts))
    return " ".join(out)


def raw_colour(name, bag):
    """The colour as Odoo names it: the product name after its bag ("CODE 3 ANTELOPE BROWN" -> "Antelope Brown").
    A name that spells the bag another way (a promo alias: "CAIRO BACKPACK BLACK" for CAIRO BP) drops as many words
    as the bag has. No colour left -> the family, else "Other"."""
    n = _norm(name)
    if n == bag:
        rest = ""
    elif n.startswith(bag + " "):
        rest = n[len(bag) + 1:]
    else:
        rest = " ".join(n.split()[len(bag.split()):])
    return _title(rest) or colours.family(n) or "Other"


def make_resolver(infer, names_cat, tiers, raw=None):
    """resolve(product name) -> (category, bag, colour) or None when it isn't a bag.

    Bag = the shared catalogue resolver (`infer`, as Push Planner / Bags on offer use); a product it
    can't place but bag_names.csv lists (a new bag), or whose name minus the colour words is such a bag
    (a new colour of it), falls back to that name. Gift bags and [REJECT] products are left out.
    Colour = as Odoo names it (raw_colour) when raw (default RAW_COLOURS), else lib/colours.family (shades fold into families).
    Category = bag_tiers.csv, else the bag's most common bag_names.csv category, else OTHER."""
    raw = RAW_COLOURS if raw is None else raw
    by_bag = defaultdict(Counter)
    for n, cat in names_cat.items():
        b = infer(n) or fallback_bag(n)
        if cat:
            by_bag[b][cat] += 1

    def resolve(name):
        n = _norm(name)
        if not n or n.startswith("GIFT BAG") or "[REJECT]" in n:      # rejects: their own page (Reject Sale)
            return None
        fb = fallback_bag(n)
        bag = infer(n) or (fb if n in names_cat or fb in by_bag else None)
        if not bag:
            return None
        cat = tiers.get(bag) or (by_bag[bag].most_common(1)[0][0] if by_bag.get(bag) else "") or "OTHER"
        col = raw_colour(n, bag) if raw else (colours.family(n) or "Other")
        return cat, bag, col
    return resolve


def bucket(daily, end, month_start):
    """{name: {date iso: units}} -> {name: {"d7", "d28", "mtd"}} for the 7 / 28 days ending `end` and
    the month to date (month_start → end)."""
    s7, s28 = end - datetime.timedelta(days=6), end - datetime.timedelta(days=WINDOW_DAYS - 1)
    out = {}
    for name, days in daily.items():
        t = {"d7": 0, "d28": 0, "mtd": 0}
        for d, u in days.items():
            d = datetime.date.fromisoformat(str(d)[:10])
            if d > end:
                continue
            if d >= s7:
                t["d7"] += u
            if d >= s28:
                t["d28"] += u
            if d >= month_start:
                t["mtd"] += u
        out[name] = t
    return out


def moves_sql(codes):
    """MOVES_SQL for one market's shop location codes (lib/stock's allow-list)."""
    inside = lambda a: "(%s.usage = 'internal' AND split_part(%s.complete_name, '/', 1) IN (%s))" % (   # noqa: E731
        a, a, ", ".join("'%s'" % c for c in codes))
    return MOVES_SQL.format(dst=inside("ld"), src=inside("ls"))


def kenya_shop_codes(base_codes):
    """lib/stock's Kenya shop codes + the shops it doesn't list yet (Machakos, Nyeri) — order kept, no repeats."""
    return tuple(dict.fromkeys(tuple(base_codes) + EXTRA_KENYA_SHOPS))


def kenya_shop_sales_filter():
    """SQL filter for the Kenya shop tills: not the Sinza / Uganda tills, not the Website, Jumia or Staff POS tills."""
    out = ", ".join("'%s'" % t for t in ("sinza", "dar-es-alam", "uganda") + KENYA_NON_SHOP_TILLS)
    return ("AND lower(COALESCE(pc.\"name\",'')) NOT IN (%s) AND lower(COALESCE(pc.\"name\",'')) NOT LIKE '%%website%%'" % out)


def sum_shops(by_shop):
    """{shop code: {name: on-hand}} -> {name: on-hand summed over the shops}, only names above 0."""
    tot = Counter()
    for names in (by_shop or {}).values():
        for n, q in names.items():
            tot[n] += q or 0
    return {n: q for n, q in tot.items() if q > 0}


def daily_series(sold_daily, net_daily, rcv_daily, day0):
    """{name: {date iso: n}} ×3 -> {name: {"s","n","r": {day index: n}}} (day index = days since day0;
    days before day0 dropped, zeros left out)."""
    out = {}
    for key, src in (("s", sold_daily), ("n", net_daily), ("r", rcv_daily)):
        for name, days in src.items():
            for d, v in days.items():
                i = (datetime.date.fromisoformat(str(d)[:10]) - day0).days
                v = int(round(v or 0))
                if i >= 0 and v:
                    e = out.setdefault(name, {"s": {}, "n": {}, "r": {}})[key]
                    e[i] = e.get(i, 0) + v
    return out


def rollup(sold, stock, resolve, daily=None):
    """Fold Odoo products into Category → Bag → Colour rows.

    sold: {name: {"d7","d28","mtd"}}, stock: {name: on-hand}, daily: daily_series() output (optional).
    Returns (rows, unmatched) where each row is {"cat","bag","col","stock","d7","d28","mtd","names"} plus
    "s","n","r" (daily sold / net shop moves / received, {day index: n}) when daily is given, and unmatched
    sums what didn't resolve to a bag."""
    daily = daily or {}
    agg, miss = {}, {"stock": 0, "d7": 0, "d28": 0, "mtd": 0}
    for name in set(sold) | set(stock) | set(daily):
        s, q = sold.get(name) or {}, int(stock.get(name) or 0)
        key = resolve(name)
        if key is None:
            miss["stock"] += q
            for p in PERIODS:
                miss[p] += int(s.get(p) or 0)
            continue
        r = agg.setdefault(key, {"cat": key[0], "bag": key[1], "col": key[2], "fam": colours.family(key[2]) or "", "stock": 0,
                                 "d7": 0, "d28": 0, "mtd": 0, "names": []})
        r["stock"] += q
        for p in PERIODS:
            r[p] += int(s.get(p) or 0)
        r["names"].append(_norm(name))
        for k, series in (daily.get(name) or {}).items():
            e = r.setdefault(k, {})
            for i, v in series.items():
                e[i] = e.get(i, 0) + v
    rows = [r for r in agg.values()
            if r["stock"] > 0 or r["d28"] > 0 or r["mtd"] > 0 or any((r.get("s") or {}).values())]
    for r in rows:
        r["stock"] = max(r["stock"], 0)
        r["names"].sort()
        if daily:
            for k in ("s", "n", "r"):
                r[k] = {str(i): v for i, v in sorted((r.get(k) or {}).items()) if v}
    rows.sort(key=lambda r: (r["cat"], r["bag"], -r["stock"], r["col"]))
    return rows, miss


def offer_tags(bags, offers, new_products=(), matcher=None):
    """{bag: [tags]} for the bags on offer (others left out).

    offers: [(offer bag name, [tags])], the month's on-offer list. A bag matches a name when it equals it or is a
    word-prefix of it either way ("AVANA" covers "AVANA HB"), or by `matcher(name)(bag)` when given (the dashboard's
    bag_classifier, which also knows its promo aliases). new_products: bag types tagged "New product"."""
    def prefix(name):
        n = _norm(name)
        return lambda b: b == n or b.startswith(n + " ") or n.startswith(b + " ")
    match = [((matcher or prefix)(n), tags) for n, tags in offers]
    new = [prefix(n) for n in new_products]
    out = {}
    for b in bags:
        tags = []
        for m, ts in match:
            if m(b):
                tags += [t for t in ts if t not in tags]
        if any(m(b) for m in new) and "New product" not in tags:
            tags.append("New product")
        if tags:
            out[b] = sorted(tags, key=lambda x: TAG_ORDER.index(x) if x in TAG_ORDER else 9)
    return out


TAG_ORDER = ("Power Deal", "Deal of the Week", "Combo", "Single offer", "New product")


def _kenya_offers(month_start):
    """[(name, tags)] from the dashboard's on-offer source for the month (bags_offer_source.json when it is that
    month, else the bags_offer_source_<YYYY-MM>.json archive), or None when neither exists."""
    for fn in ("bags_offer_source.json", f"bags_offer_source_{month_start:%Y-%m}.json"):
        try:
            with open(os.path.join(DASHBOARD, fn), encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        if d.get("onOffer") and (fn != "bags_offer_source.json" or d.get("month") == f"{month_start:%B %Y}"):
            return [(n, ["Combo" if t == "Combo component" else t for t in ts]) for n, ts in d["onOffer"].items()]
    return None


def _market_offers(month_start, mk):
    """[(bag, tags)] for Sinza / Uganda from the dashboard's offers_monthly.csv (Combo / Single offer), or None."""
    from lib import receipt_combos as rc
    o = rc.load_offers(f"{month_start:%B}", mk)
    if not o:
        return None
    out = []
    for kind, tag in (("combos", "Combo"), ("singles", "Single offer")):
        for offer in o.get(kind, []):
            for slot in offer["slots"]:
                out += [("LAPTOP SLEEVE" if b == "*SLEEVE" else b.lstrip("*"), [tag]) for b in slot]
    return out


def _new_products():
    """This month's new products as the Bags on offer page lists them (BOO.newProducts), else new_products.txt."""
    try:
        with open(os.path.join(DASHBOARD, "bags_on_offer.html"), encoding="utf-8") as f:
            m = re.search(r"const BOO = (.*?);\n</script>", f.read(), re.S)
        names = json.loads(m.group(1)).get("newProducts") if m else None
        if names:
            return [_norm(n) for n in names]
    except (OSError, ValueError):
        pass
    try:                                                     # shared/: the list copied from that page
        with open(os.path.join(DASHBOARD, "new_products.json"), encoding="utf-8") as f:
            names = json.load(f).get("newProducts")
        if names:
            return [_norm(n) for n in names]
    except (OSError, ValueError):
        pass
    from lib import new_products_list
    return [_norm(n) for n in new_products_list.names()]


def month_starts(day0, today):
    """First day of every month from day0's to today's."""
    m, out = day0.replace(day=1), []
    while m <= today:
        out.append(m)
        m = (m.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    return out


def periods(today, m_start, m_end):
    """The Marketing dashboard's periods (bags_on_offer._base_windows): Monthly = the live month to date,
    Weekly = this Sun–Sat week to date, Last week = the previous full Sun–Sat week. {key: [start, upto] iso}."""
    ws = today - datetime.timedelta(days=(today.weekday() + 1) % 7)            # Sunday of this week
    d = datetime.timedelta
    return {"monthly": [m_start.isoformat(), min(m_end, today).isoformat()],
            "weekly": [ws.isoformat(), today.isoformat()],
            "lastweek": [(ws - d(days=7)).isoformat(), (ws - d(days=1)).isoformat()]}


def load_offers(bags_by_market, day0, today, matcher=None):
    """{market: {"YYYY-MM": {bag: [tags]}}} for every month in the data window that has an offer list.
    New products are tagged in the current month only (the dashboard keeps no older list)."""
    new = _new_products()
    cur = today.replace(day=1)
    out = {}
    for mk, bags in bags_by_market.items():
        out[mk] = {}
        for ms in month_starts(day0, today):
            lst = _kenya_offers(ms) if mk == "kenya" else _market_offers(ms, mk)
            if lst is not None:
                out[mk][f"{ms:%Y-%m}"] = offer_tags(bags, lst, new if ms == cur else (),
                                                    matcher=matcher if mk == "kenya" else None)
    return out


def load(today=None):
    """Per market: rows + unmatched. None if Odoo is unreachable."""
    from lib import db, report_month, stock as lstock
    import self_made_combos as smc

    ok, msg = db.check_connection()
    if not ok:
        print(f"  DB unreachable — {msg}")
        return None
    today = today or datetime.date.today()
    end = today - datetime.timedelta(days=1)                         # last full day
    m_start, m_end = report_month.live_month_window()
    day0 = min(today - datetime.timedelta(days=DAILY_DAYS - 1), m_start)   # Stock rate data starts here
    start = min(end - datetime.timedelta(days=WINDOW_DAYS - 1), m_start, day0)
    infer, _ = smc.bag_classifier(set())
    resolve = make_resolver(infer, _bag_names(), _tiers())
    sql = {"kenya": smc._bag_sales_daily_sql(kenya_shop_sales_filter()), "sinza": smc.BAG_SALES_DAILY_SINZA_SQL,
           "uganda": smc.BAG_SALES_DAILY_UGANDA_SQL}
    markets = {}
    for mk, label in MARKETS:
        df = db.run_query_cached(sql[mk], {"s": start, "e": today}, ttl_min=30)   # today too: Stock rate is "to date"
        daily = defaultdict(dict)
        for r in ([] if df is None else df.itertuples(index=False)):
            daily[str(r.name)][str(r.d)[:10]] = daily[str(r.name)].get(str(r.d)[:10], 0) + int(r.units or 0)
        sold = bucket(daily, end, m_start)
        codes = kenya_shop_codes(lstock.KENYA_SHOP_CODES) if mk == "kenya" else lstock._codes_for(mk)
        stock = sum_shops(lstock.odoo_stock_by_shop_code(codes, positive_only=False))
        net, rcv = defaultdict(dict), defaultdict(dict)
        mv = db.run_query_cached(moves_sql(codes), {"s": day0}, ttl_min=30)
        for r in ([] if mv is None else mv.itertuples(index=False)):
            net[str(r.name)][str(r.d)[:10]] = float(r.net or 0)
            rcv[str(r.name)][str(r.d)[:10]] = float(r.rcv or 0)
        rows, miss = rollup(sold, stock, resolve, daily_series(daily, net, rcv, day0))
        markets[mk] = {"label": label, "rows": rows, "unmatched": miss}
    offers = load_offers({mk: sorted({r["bag"] for r in m["rows"]}) for mk, m in markets.items()}, day0, today,
                         matcher=lambda n: smc.bag_classifier({n})[1])
    fmt = lambda d: d.strftime("%d %b")                               # noqa: E731
    windows = {"d7": [fmt(end - datetime.timedelta(days=6)), fmt(end)],
               "d28": [fmt(end - datetime.timedelta(days=WINDOW_DAYS - 1)), fmt(end)],
               "mtd": [fmt(m_start), fmt(end)] if m_start <= end else None}
    return {"generated": datetime.datetime.now().strftime("%d %b %Y %H:%M"), "end": end.isoformat(),
            "windows": windows, "markets": markets, "day0": day0.isoformat(), "today": today.isoformat(),
            "periods": periods(today, m_start, m_end), "offers": offers}


def inject(payload):
    with open(HTML, encoding="utf-8") as f:
        html = f.read()
    block = ("<!-- CC_DATA_START -->\n<script>\nconst CC = "
             + json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
             + ";\n</script>\n<!-- CC_DATA_END -->")
    html = re.sub(r"<!-- CC_DATA_START -->.*?<!-- CC_DATA_END -->", lambda _m: block, html, flags=re.S)
    with open(HTML, "w", encoding="utf-8") as f:
        f.write(html)


if __name__ == "__main__":
    p = load()
    if p is None:
        raise SystemExit(1)
    for mk, m in p["markets"].items():
        bags = {r["bag"] for r in m["rows"]}
        print(f"  Colour Comparison {m['label']}: {len(bags)} bags, {len(m['rows'])} bag colours, "
              f"stock {sum(r['stock'] for r in m['rows']):,}, sold 28 d {sum(r['d28'] for r in m['rows']):,} "
              f"(not a bag: stock {m['unmatched']['stock']:,}, sold {m['unmatched']['d28']:,})")
    inject(p)
    if os.environ.get("DENRI_LAUNCHER") != "1":
        webbrowser.open("file://" + HTML)
