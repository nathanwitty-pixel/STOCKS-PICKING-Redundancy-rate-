"""sync_from_dashboard.py — refresh shared/ from the Marketing_dashboard folder next to this one.

shared/ holds the pieces of the dashboard this app needs when the dashboard isn't there (Streamlit Cloud): lib/,
the sales SQL + bag resolver from self_made_combos.py, the bag lists, the offer lists, the new-products list, the look
files and the owner. Run it after the dashboard's offers / bags change, then commit and push shared/.

    python sync_from_dashboard.py
"""
import json
import os
import re
import shutil

BASE = os.path.dirname(os.path.abspath(__file__))
_CANDIDATES = (os.path.join(os.path.dirname(BASE), "Marketing_dashboard"),
               os.path.join(os.path.expanduser("~"), "Desktop", "Marketing_dashboard"))
SRC = os.environ.get("DASHBOARD_DIR") or next((d for d in _CANDIDATES if os.path.isdir(d)), _CANDIDATES[0])
# The dashboard keeps its files in sub-folders now (data/, assets/, generators/, html/); older copies had them at the top.
SUBDIRS = ("", "data", "assets", "generators", "html")
DST = os.path.join(BASE, "shared")
LIB = ("__init__.py", "db.py", "stock.py", "colours.py", "report_month.py", "receipt_combos.py", "new_products_list.py")
FILES = ("bag_original_prices.json", "bag_names.csv", "bag_tiers.csv", "offers_monthly.csv", "new_products.txt",
         "v5_theme.css", "v5_theme.js", "top_nav.js", "kpi_drag.js")


def _block(src, start, end_marker):
    i = src.index(start)
    return src[i:src.index(end_marker, i + len(start))].rstrip() + "\n"


def slim_self_made_combos(src):
    """The sales SQL and the bag resolver from the dashboard's self_made_combos.py, word for word."""
    return ('"""self_made_combos.py — the parts of the Marketing dashboard\'s self_made_combos.py that Stocks Picking uses, copied\n'
            'word for word (refresh with sync_from_dashboard.py): the per-day bag sales SQL for each market and the bag resolver\n'
            '(bag_classifier, on bag_original_prices.json). Everything else of that page is not needed here."""\n'
            "import json\nimport os\nimport re\n\n_BAG_PRICES = None\n\n\n"
            + _block(src, "def _load_bag_prices():", "\n# Standalone bag sales") + "\n\n"
            + _block(src, "def _bag_sales_daily_sql(market_sql):", "\ndef bag_classifier(") + "\n\n"
            + _block(src, "def bag_classifier(on_offer_raw):", "\ndef _bags_not_on_offer("))


def _find(name):
    """Path of a dashboard file, wherever its layout keeps it."""
    for d in SUBDIRS:
        p = os.path.join(SRC, d, name)
        if os.path.isfile(p):
            return p
    raise SystemExit(f"{name} not found in {SRC}")


def main():
    _find("self_made_combos.py")
    # Code (lib/ and the sales SQL) is copied only from the old flat layout: the new dashboard's code reads its files
    # through lib/paths.py and uses its own SQL helpers (POS_LINES), which shared/ doesn't have, so the working
    # shared/ copies are kept. Only the data (offer lists, bag lists, look files) is refreshed.
    flat = os.path.isfile(os.path.join(SRC, "self_made_combos.py"))
    if flat:
        os.makedirs(os.path.join(DST, "lib"), exist_ok=True)
        for f in LIB:
            shutil.copy2(os.path.join(SRC, "lib", f), os.path.join(DST, "lib", f))
        with open(os.path.join(SRC, "self_made_combos.py"), encoding="utf-8") as f:
            slim = slim_self_made_combos(f.read())
        with open(os.path.join(DST, "self_made_combos.py"), "w", encoding="utf-8") as f:
            f.write(slim)
    for f in FILES:
        shutil.copy2(_find(f), os.path.join(DST, f))
    off_dir = os.path.dirname(_find("bags_offer_source.json"))
    offers = [f for f in os.listdir(off_dir) if re.fullmatch(r"bags_offer_source(_\d{4}-\d{2})?\.json", f)]
    for f in offers:
        shutil.copy2(os.path.join(off_dir, f), os.path.join(DST, f))
    with open(_find("dashboard_pages.json"), encoding="utf-8") as f:
        owner = json.load(f).get("owner", {})
    with open(os.path.join(DST, "dashboard_pages.json"), "w", encoding="utf-8") as f:
        json.dump({"owner": owner}, f, ensure_ascii=False, indent=2)
    with open(_find("bags_on_offer.html"), encoding="utf-8") as f:
        m = re.search(r"const BOO = (.*?);\n</script>", f.read(), re.S)
    names = (json.loads(m.group(1)).get("newProducts") or []) if m else []
    with open(os.path.join(DST, "new_products.json"), "w", encoding="utf-8") as f:
        json.dump({"newProducts": names}, f, indent=2)
    print(f"  shared/ refreshed from {SRC}: lib ({len(LIB) if flat else 'kept'}), {len(FILES)} files, {len(offers)} offer lists, "
          f"{len(names)} new products. Commit and push shared/ to update Streamlit Cloud.")


if __name__ == "__main__":
    main()
