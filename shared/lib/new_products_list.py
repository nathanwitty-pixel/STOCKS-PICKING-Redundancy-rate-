"""lib/new_products_list.py — which bag types count as this month's NEW PRODUCTS.

Source: new_products.txt at the project root (editable, one bag type per line).
It wins over the ✅ ticks in MONTHLY_TARGET col I; when the file is missing or
empty, callers keep using those ticks.
"""
import os as _os

_FILE = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "new_products.txt")


def names():
    """Upper-cased bag types from new_products.txt in file order ([] = use the sheet ticks)."""
    out = []
    try:
        with open(_FILE, encoding="utf-8") as f:
            for line in f:
                s = line.split("#", 1)[0].strip().upper()
                if s and s not in out:
                    out.append(s)
    except OSError:
        pass
    return out
