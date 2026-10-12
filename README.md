# STOCKS PICKING (Redundancy rate) — every bag's colours side by side (Kenya · Sinza · Uganda)

> **Live version (12 Oct 2026): the Marketing dashboard's Marketing › Stocks Picking menu**
> (`..\Marketing_dashboard\stocks_picking.py` / `stocks_picking.html`, spec `docs/stocks-picking.md`). It refreshes from
> Odoo like the other menus and runs on Streamlit. Make changes there; the files in this folder are the original copy.

The live version of the marketing team's **"colour comparison"** sheet (MARKETING_WORK_PLAN →
"(MARKETING TEAM INFO) STOCKS PICKING (Redundancy rate)"): Category → Bag → Colour, with each colour's
redundancy rate and stock level, plus an AVERAGE % row per bag. The data comes from Odoo instead of
hand-made sheet tabs, and covers all three markets: switch with the **Markets** picker in the page sidebar.

## Files (this folder)

| File | What it is |
|---|---|
| `colour_comparison.html` | The page. Open it in a browser. |
| `colour_comparison.py` | Rebuilds the page with fresh Odoo data (sales, stock, stock moves, offer lists): `python colour_comparison.py` (`DENRI_LAUNCHER=1` = don't open the browser). Data marker `<!-- CC_DATA_START -->…<!-- CC_DATA_END -->` (const `CC`). |
| `page_sidebar.js`, `chart_switcher.js` | Copies of the dashboard's sidebar and chart-type menu, so the page works on its own. |
| `tests/test_colour_comparison.py` | `python -m pytest tests -q` |

**Depends on the Marketing dashboard folder** (`..\Marketing_dashboard`, or set `DASHBOARD_DIR`). From there it uses
the Odoo connection (`.env`), `lib/` (stock, colours, db, report month), the `self_made_combos.py` sales queries and
bag resolver, and `bag_names.csv` / `bag_tiers.csv`. Use the dashboard's Python: `C:\ProgramData\anaconda3\python.exe`.
This page is **not** a menu in the dashboard.

## The number: redundancy rate

**Redundancy %** = (stock − sold) ÷ stock, the sheet's formula. It is the share of today's stock that the
period's sales didn't cover:
- 100 % = nothing sold;
- 0 % = it sold as many as it holds;
- below 0 = it sold more than it has in stock (restock).

It is reverse-checked against the sheet: PIONEER Brown, stock 79 with 8 sold → 71/79 = 89.87 %.

The **bag row** (and category row) shows the **average of its colours' rates**, like the sheet's
"AVERAGE %" total row: ANTITHEFT (9.40 + 1.43 + 61.22 + 26.67 + 100) ÷ 5 = 39.74 %. A colour with no stock has no
rate ("—") and is left out of the average.

Colours: green < 50 %, amber 50–80 %, red ≥ 80 %.

## Inputs (read only)

| Signal | From |
|---|---|
| Units sold per product per day, per market | Odoo POS: `self_made_combos.BAG_SALES_DAILY_SQL` / `_SINZA_` / `_UGANDA_` (combo wrappers `+`, delivery, customisation, straps and gift bags are left out, as on Push Planner) |
| Live stock per product, per market | `lib/stock.odoo_stock_by_product(market)`: shop stock only (Kenya = the 16 shop codes, Sinza = DAR, Uganda = UG) |
| Bag type | `self_made_combos.bag_classifier()` |
| Colour | `lib/colours.family()`: shades fold into families (Chocolate / Spice / Antelope → Brown, Nude → Beige, CN / TT / 018 → base colour) |
| Category | `bag_tiers.csv`, else the bag's most common `bag_names.csv` category, else OTHER |

**Left out:** gift bags, and `[REJECT]` products (the dashboard's Reject Sale page covers them).

A bag the price catalogue doesn't know yet (e.g. LAFEMME) still shows if `bag_names.csv` lists it, or lists another
colour of it. Everything else (wipes, cleaners, laptop sleeves, promo items) is counted as "not a bag" in the build log.

## Periods

**Last 7 days** (default, closest to the sheet), **Last 28 days**, **This month**. All end yesterday, the last
full day. Stock is always live (now).

## Other columns

| Column | Meaning |
|---|---|
| **Sold** / **Stock** | units sold in the period / live shop stock |
| **Sales mix** / **Stock mix** | the colour's share of its bag's units sold / stock (green when sales mix is ≥ 10 points above stock mix, red when ≥ 10 below) |
| **Days cover** | stock ÷ (sold in the last 28 days ÷ 28) |

## Signals (one per colour, first that fits)

| Signal | When |
|---|---|
| **Restock** | sold ≥ *minSold* in the last 28 days and < 14 days of cover |
| **Push** | stock ≥ *floor* and redundancy ≥ 90 % in the period |
| **Best colour** | the bag's lowest-redundancy colour (≥ 2 sold, bag has 2+ colours), if it has no other signal |

| Market | floor | minSold |
|---|---|---|
| Kenya | 10 | 4 |
| Sinza | 3 | 2 |
| Uganda | 3 | 2 |

These are `RULE`, `COVER_DAYS` and `PUSH_RED` at the top of the page script.

## Stock rate (section at the bottom of the page)

**Sold rate** = units sold in the period ÷ the shop stock there on the **morning of its first day**, per colour,
bag (totals, not an average), category and market, beside **Stock now** (live) and the bag's **offer** status.

| Column | Meaning |
|---|---|
| **Stock at start** | stock now − the net done stock moves in/out of the market's shops from the first day to now (`MOVES_SQL`; moves between two of its shops cancel). A rebuild below 0 counts as 0. |
| **Received** | units moved into the shops during the period from anywhere but a customer (deliveries, transfers) |
| **Sold** | POS units in the period (same query as the rest of the page, up to today) |
| **Sold rate** | sold ÷ stock at start; over 100 % = received stock sold too; "new stock" = nothing there on day 1 but it sold |
| **Offer** | from the Marketing dashboard, for the month the period ends in. Kenya: `bags_offer_source.json` / `bags_offer_source_<YYYY-MM>.json` `onOffer` (Power Deal, Deal of the Week, Combo = combo component), matched with `bag_classifier`. Sinza / Uganda: `offers_monthly.csv` (Combo, Single offer). Plus this month's new products (`BOO.newProducts` in `bags_on_offer.html`). No tag = **Not on offer**. If the dashboard has no list for that month, the latest earlier one is used and the page says so. |

**Periods** are the dashboard's (Bags on offer): **Monthly** = the live month to date, **Weekly** = this Sun–Sat week
to date, **Last week** (default) = the last full Sun–Sat week, **Custom** = any From–To inside the data window. The
page ships `DAILY_DAYS` = 120 days of daily sold / net moves / received per colour (`s`, `n`, `r` by day index from
`CC.day0`), so every period is worked out in the browser. Remembered per browser (`localStorage` key `spr-rate`).

Reverse check (Kenya, last week 4–10 Oct 2026): BABY BAG Brown 28 at start + 4 received − 3 sold = 29 now; Kenya
10,295 at start, 3,496 sold → 34.0 % (on offer 38.3 %, not on offer 17.9 %).

## Page

1. **KPI tiles:** stock in shops, units sold, the market's redundancy rate (all stock, plus the average of bags), the
   least and most redundant colour family, and the colours to act on.
2. **Colour mix:** each colour family's share of stock beside its share of sales, with a table of redundancy, sold,
   stock and the gap.
3. **Colours to act on:** Restock (lowest cover first) and Push (most stock first), 15 each.
4. **Colour comparison by bag:** the grouped table, with category chips, search, sort, "only bags with a colour to act
   on" and fold/unfold. Hover a colour to see the Odoo products folded into it.

5. **Stock rate:** see above. Every column is sortable (click its name; again to reverse) and filterable from the row
   under the headers: Bag / colour (text), Offer (All, On offer, Not on offer or one tag, also the chips above), and
   the number columns (`>50`, `<10`, `>=5`, `=0`, `10-50`, or a plain number = at least; Sold rate in %; an invalid
   entry turns red and is ignored). **Filter: Bags** tests each bag's totals and keeps all its colours; **Colours**
   tests each colour and keeps only those that pass (the bag shows "2 of 5 colours"). Clear filters resets them.
   Sort, filters and the Bags / Colours choice are remembered in `spr-rate`.

The chosen market and period are remembered in the browser (`localStorage` key `spr-state`).
