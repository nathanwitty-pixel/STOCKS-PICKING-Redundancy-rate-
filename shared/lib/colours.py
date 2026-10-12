"""lib/colours.py — colour FAMILY of a product (Brown, Black, Red, Beige, Grey, …).

Source of truth: bag_names.csv — a saved snapshot of the main spreadsheet's `bag_names` tab
(CATEGORY, PRODUCT NAME, COLOUR), so the sheet is never read at run time. It folds every shade
into its family the way the business groups colours: Chocolate / Spice / Mustard / Cracked /
Dark Brown / Yellow Dotted → Brown; CN / TT / Croc / 018 editions → their base colour; Nude →
Beige; Maroon → Red; Lilac → Pink …

Used everywhere a page shows colours EXCEPT New Products, which keeps the exact colour on
purpose (it tracks which specific colours of a new bag move).

To refresh after the sheet changes: re-export the tab to bag_names.csv (same three columns).
"""
import csv
import os
import re
from collections import Counter, defaultdict

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BAG_NAMES_FILE = os.path.join(_BASE, "bag_names.csv")

_MAP = None          # NORM(product name) -> family
_WORDS = None        # colour word -> family (learnt from the file, for names it doesn't list)


def _norm(s):
    return re.sub(r"\s+", " ", re.sub(r"\[\s*REJECT\s*\]", " ", str(s), flags=re.I).upper().replace(".", " ")).strip()


def _load():
    global _MAP, _WORDS
    if _MAP is not None:
        return
    _MAP, votes = {}, defaultdict(Counter)
    try:
        with open(BAG_NAMES_FILE, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                name, fam = _norm(r.get("PRODUCT NAME", "")), str(r.get("COLOUR", "")).strip()
                if not name or not fam or "TOTAL" in name:
                    continue
                _MAP[name] = fam
                for w in re.split(r"[^A-Z0-9]+", name):
                    if w and not w.isdigit():
                        votes[w][fam] += 1
    except OSError:
        pass
    # A word "belongs" to a family only when that family clearly dominates it (bag-type words like
    # ZULA appear under every colour, so they never qualify).
    _WORDS = {}
    for w, c in votes.items():
        fam, n = c.most_common(1)[0]
        if n >= 2 and n / sum(c.values()) >= 0.8:
            _WORDS[w] = fam
    _WORDS.setdefault("CHOCO", "Brown")


def family(product_name, fallback=""):
    """Colour family for a product name (Odoo or sheet spelling; "[REJECT]" ignored).
    Exact bag_names entry first (also via product_aliases.csv), else the last colour word in the
    name the file clearly assigns to one family, else `fallback`."""
    _load()
    n = _norm(product_name)
    if n in _MAP:
        return _MAP[n]
    try:
        from . import odoo_tabs
        a = odoo_tabs.base_name(product_name)
        if a in _MAP:
            return _MAP[a]
    except Exception:                                        # noqa: BLE001
        pass
    for w in reversed([w for w in re.split(r"[^A-Z0-9]+", n) if w]):
        if w in _WORDS:
            return _WORDS[w]
    return fallback
