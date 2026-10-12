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
SRC = os.environ.get("DASHBOARD_DIR") or os.path.join(os.path.dirname(BASE), "Marketing_dashboard")
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


def main():
    if not os.path.isfile(os.path.join(SRC, "self_made_combos.py")):
        raise SystemExit(f"Marketing dashboard not found at {SRC} (set DASHBOARD_DIR)")
    os.makedirs(os.path.join(DST, "lib"), exist_ok=True)
    for f in LIB:
        shutil.copy2(os.path.join(SRC, "lib", f), os.path.join(DST, "lib", f))
    for f in FILES:
        shutil.copy2(os.path.join(SRC, f), os.path.join(DST, f))
    offers = [f for f in os.listdir(SRC) if re.fullmatch(r"bags_offer_source(_\d{4}-\d{2})?\.json", f)]
    for f in offers:
        shutil.copy2(os.path.join(SRC, f), os.path.join(DST, f))
    with open(os.path.join(SRC, "self_made_combos.py"), encoding="utf-8") as f:
        slim = slim_self_made_combos(f.read())
    with open(os.path.join(DST, "self_made_combos.py"), "w", encoding="utf-8") as f:
        f.write(slim)
    with open(os.path.join(SRC, "dashboard_pages.json"), encoding="utf-8") as f:
        owner = json.load(f).get("owner", {})
    with open(os.path.join(DST, "dashboard_pages.json"), "w", encoding="utf-8") as f:
        json.dump({"owner": owner}, f, ensure_ascii=False, indent=2)
    with open(os.path.join(SRC, "bags_on_offer.html"), encoding="utf-8") as f:
        m = re.search(r"const BOO = (.*?);\n</script>", f.read(), re.S)
    names = (json.loads(m.group(1)).get("newProducts") or []) if m else []
    with open(os.path.join(DST, "new_products.json"), "w", encoding="utf-8") as f:
        json.dump({"newProducts": names}, f, indent=2)
    print(f"  shared/ refreshed from {SRC}: lib ({len(LIB)}), {len(FILES)} files, {len(offers)} offer lists, "
          f"{len(names)} new products. Commit and push shared/ to update Streamlit Cloud.")


if __name__ == "__main__":
    main()
