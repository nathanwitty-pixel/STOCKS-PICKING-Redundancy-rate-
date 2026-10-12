"""lib/receipt_combos.py — Sinza & Uganda combos counted from POS receipts.

Those tills ring every bag as its own line; a client printed out with more than one bag bought a combo.
Per receipt (refunded receipts dropped; >= BULK_MIN bags = bulk, never a combo): bags at one shared unit
price (rounded to 10) = a combo per price; the bags left over = one more combo if two or more (Uganda
splits a combo's price unevenly), a single if one. A combo
whose bag types fill a listed combo's slots (offers_monthly.csv; same count, any order, alternatives)
is RUNNING, otherwise SELF-MADE. Spec: docs/self-made-combos.md › Sinza & Uganda.
"""
import csv
import datetime
import itertools
import os

from . import db

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OFFERS_CSV = os.path.join(BASE, "offers_monthly.csv")
BULK_MIN = 5
TILLS = {"sinza": ("sinza", "dar-es-alam"), "uganda": ("uganda",)}
_SKIP = ("DELIVERY", "GIFT BAG", "DISCOUNT", "CUSTOMI", "STRAP")

RECEIPT_LINES_SQL = """
SELECT o.id AS receipt, o."name" AS ref, o.date_order::date AS d, pt."name" AS product, pl.qty AS qty,
       pl.price_subtotal_incl AS amount
FROM pos_order o
JOIN pos_order_line pl ON pl.order_id = o.id
JOIN pos_session ps ON ps.id = o.session_id
JOIN pos_config pc ON pc.id = ps.config_id
JOIN product_product pp ON pp.id = pl.product_id
JOIN product_template pt ON pt.id = pp.product_tmpl_id
WHERE lower(pc."name") IN :tills
  AND o.state IN ('paid', 'done', 'invoiced')
  AND o.date_order::date BETWEEN :s AND :e
"""


def load_offers(month_name, market):
    """{'combos': [...], 'singles': [...]} for the month/market from offers_monthly.csv, or None.
    Each offer: {name, slots: [set(bag types)], was, now, disc, currency, wasKsh, nowKsh}."""
    try:
        with open(OFFERS_CSV, encoding="utf-8", newline="") as f:
            rows = [r for r in csv.DictReader(f)
                    if r["Month"].strip().lower() == month_name.lower() and r["Market"].strip().lower() == market]
    except OSError:
        return None
    if not rows:
        return None

    def num(v):
        try:
            return int(float(str(v).replace(",", "") or 0))
        except ValueError:
            return 0
    out = {"combos": [], "singles": []}
    for r in rows:
        o = {"name": r["Name"].strip(), "slots": [{x.strip().upper() for x in s.split("/") if x.strip()}
                                                   for s in r["Bags"].split("+")],
             "was": num(r["Was"]), "now": num(r["Now"]), "disc": num(r["Disc"]), "currency": r["Currency"],
             "wasKsh": num(r["Was KSH"]), "nowKsh": num(r["Now KSH"])}
        out["combos" if r["Type"].strip().lower() == "combo" else "singles"].append(o)
    return out


def bag_key(name, infer):
    """Catalogue bag type of a POS product (None = not a bag). Any sleeve → '*SLEEVE'."""
    n = str(name).upper()
    if any(k in n for k in _SKIP):
        return None
    if "SLEEVE" in n:
        return "*SLEEVE"
    return infer(name)


def _fits(bags, slots):
    """Bag types fill the offer's slots one-to-one in some order (alternatives per slot)."""
    if len(bags) != len(slots):
        return False
    return any(all(b in slots[i] for b, i in zip(bags, perm)) for perm in itertools.permutations(range(len(slots))))


def _receipts(lines, infer):
    """Receipt lines → {receipt: {d, bags: [(bag, unit)], ref}} with refunded receipts dropped; also the refund count."""
    by_r, refunded = {}, set()
    for ln in lines:
        k = bag_key(ln["product"], infer)
        ref = str(ln.get("ref") or "")
        if ref.upper().endswith(" REFUND"):
            refunded.add(ref[:-len(" REFUND")].strip())          # cancels its original receipt
            continue
        q = int(round(float(ln["qty"] or 0)))
        if not k or q <= 0:
            continue
        unit = int(round(float(ln["amount"] or 0) / q, -1))     # to the nearest 10: 40,000 = 40,001
        rec = by_r.setdefault(ln["receipt"], {"d": ln["d"], "bags": [], "ref": ref})
        rec["bags"] += [(k, unit)] * q
    return {k: v for k, v in by_r.items() if not v["ref"] or v["ref"] not in refunded}, refunded


def _groups(bags):
    """One receipt's [(bag, unit)] → ([(bags, revenue)] combos, [(bag, unit)] singles): same unit price = a
    combo per price; two or more leftover bags at different prices = one more combo; one leftover = a single."""
    groups = {}
    for k, unit in bags:
        groups.setdefault(unit, []).append(k)
    combos, left = [], []
    for unit, bs in groups.items():
        if len(bs) >= 2:
            combos.append((bs, unit * len(bs)))
        else:
            left.append((bs[0], unit))
    if len(left) >= 2:                        # sold together at different prices = one combo
        combos.append(([b for b, _ in left], sum(u for _, u in left)))
        left = []
    return combos, left


def offer_split(lines, offers, infer):
    """On / not on offer for Sinza / Uganda (docs/bags-on-offer.md › Sinza & Uganda): every combo (running or
    self-made) and single sales of a bag on the market's listed singles are ON offer; every other single is NOT
    on offer; 5+ bag receipts are bulk (others). Returns {combos: {running: {count, bags, revenue}, selfMade:
    {…}}, onSingles: {bag: {units, revenue}}, offSingles: {bag: {units, revenue, comboBag}}, bulk: {receipts,
    bags, revenue}, comboBags: {bag: units in self-made combos}, bags, revenue}."""
    recs, _ = _receipts(lines, infer)
    listed_singles = {b for o in (offers or {}).get("singles", []) for slot in o["slots"] for b in slot}
    listed_combo_bags = {b for o in (offers or {}).get("combos", []) for slot in o["slots"] for b in slot}
    out = {"combos": {"running": {"count": 0, "bags": 0, "revenue": 0}, "selfMade": {"count": 0, "bags": 0, "revenue": 0}},
           "onSingles": {}, "offSingles": {}, "bulk": {"receipts": 0, "bags": 0, "revenue": 0}, "comboBags": {},
           "bags": sum(len(v["bags"]) for v in recs.values()),
           "revenue": sum(u for v in recs.values() for _, u in v["bags"])}
    for rec in recs.values():
        if len(rec["bags"]) >= BULK_MIN:
            out["bulk"]["receipts"] += 1
            out["bulk"]["bags"] += len(rec["bags"])
            out["bulk"]["revenue"] += sum(u for _, u in rec["bags"])
            continue
        combos, left = _groups(rec["bags"])
        for bags, rev in combos:
            running = any(_fits(bags, o["slots"]) for o in (offers or {}).get("combos", []))
            c = out["combos"]["running" if running else "selfMade"]
            c["count"] += 1
            c["bags"] += len(bags)
            c["revenue"] += rev
            if not running:
                for b in bags:
                    out["comboBags"][b.lstrip("*")] = out["comboBags"].get(b.lstrip("*"), 0) + 1
        for b, unit in left:
            side = out["onSingles"] if b in listed_singles else out["offSingles"]
            e = side.setdefault(b.lstrip("*"), {"units": 0, "revenue": 0})
            e["units"] += 1
            e["revenue"] += unit
            if side is out["offSingles"]:
                e["comboBag"] = b in listed_combo_bags
    return out


def classify(lines, offers, infer, month_start):
    """lines: [{receipt, d, product, qty, amount}] → per-market summary:
    {running: {offer: {count, revenue, weeks{wk: n}}}, selfMade: {label: {...}}, singles: {bag: {...}},
     singlesOffer: {offer: {...}}, bulk: {receipts, bags, revenue}, receipts, comboReceipts}."""
    anchor = month_start - datetime.timedelta(days=(month_start.weekday() + 1) % 7)   # Sunday on/before day 1
    by_r, refunded = _receipts(lines, infer)
    out = {"running": {}, "selfMade": {}, "singles": {}, "singlesOffer": {},
           "bulk": {"receipts": 0, "bags": 0, "revenue": 0}, "receipts": len(by_r), "comboReceipts": 0,
           "refunded": len(refunded),
           "bags": sum(len(v["bags"]) for v in by_r.values()),               # every bag the till sold
           "revenue": sum(u for v in by_r.values() for _, u in v["bags"])}

    def bump(table, key, units, rev, wk, day=None):
        e = table.setdefault(key, {"count": 0, "revenue": 0, "weeks": {}, "days": {}})
        e["count"] += 1
        e["revenue"] += rev
        e["weeks"][wk] = e["weeks"].get(wk, 0) + 1
        if day:
            e["days"][day] = e["days"].get(day, 0) + 1          # the receipt date, for "sold on"
        if units is not None:
            e.setdefault("bags", units)

    for rec in by_r.values():
        d = rec["d"] if isinstance(rec["d"], datetime.date) else datetime.date.fromisoformat(str(rec["d"])[:10])
        wk = (d - anchor).days // 7 + 1
        if len(rec["bags"]) >= BULK_MIN:
            out["bulk"]["receipts"] += 1
            out["bulk"]["bags"] += len(rec["bags"])
            out["bulk"]["revenue"] += sum(u for _, u in rec["bags"])
            continue
        combos, left = _groups(rec["bags"])     # [(bags, revenue)], [(bag, price)]
        for bags, rev in combos:
            offer = next((o["name"] for o in (offers or {}).get("combos", []) if _fits(bags, o["slots"])), None)
            if offer:
                bump(out["running"], offer, None, rev, wk, d.isoformat())
            else:
                label = " + ".join(sorted(b.lstrip("*") for b in bags))
                bump(out["selfMade"], label, sorted(bags), rev, wk, d.isoformat())
        for b, unit in left:
            bump(out["singles"], b.lstrip("*"), None, unit, wk)
            offer = next((o["name"] for o in (offers or {}).get("singles", []) if b in o["slots"][0]), None)
            if offer:
                bump(out["singlesOffer"], offer, None, unit, wk)
        out["comboReceipts"] += bool(combos)
    return out


def market_lines(market, start, end):
    """Receipt lines for a market's tills between start and end (inclusive), or None if offline."""
    try:
        df = db.run_query(RECEIPT_LINES_SQL.replace(":tills", "(" + ", ".join("'" + t + "'" for t in TILLS[market]) + ")"),
                          {"s": start.isoformat(), "e": end.isoformat()})
    except Exception as e:                                   # noqa: BLE001
        print(f"  {market} receipts unavailable: {e}")
        return None
    if df is None:
        return None
    return [{"receipt": r.receipt, "ref": r.ref, "d": r.d, "product": r.product, "qty": r.qty, "amount": r.amount}
            for r in df.itertuples(index=False)]


def market_summary(market, month_start, month_end, infer, month_name=None):
    """classify() for a market's tills over the month, with that month's offers; None if offline."""
    offers = load_offers(month_name or month_start.strftime("%B"), market)
    try:
        df = db.run_query(RECEIPT_LINES_SQL.replace(":tills", "(" + ", ".join("'" + t + "'" for t in TILLS[market]) + ")"),
                          {"s": month_start.isoformat(), "e": month_end.isoformat()})
    except Exception as e:                                   # noqa: BLE001
        print(f"  {market} receipts unavailable: {e}")
        return None
    if df is None:
        return None
    lines = [{"receipt": r.receipt, "ref": r.ref, "d": r.d, "product": r.product, "qty": r.qty, "amount": r.amount}
             for r in df.itertuples(index=False)]
    return {"offers": offers, **classify(lines, offers, infer, month_start)}
