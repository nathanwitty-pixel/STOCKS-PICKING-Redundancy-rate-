# STOCKS PICKING (Redundancy rate) — every bag's colours side by side (Kenya · Sinza · Uganda)

> **Streamlit app (12 Oct 2026):** double-click `Stocks Picking app.bat` (or `python streamlit_app.py`) →
> http://localhost:8502. It reloads from Odoo like the Marketing dashboard: **Refresh** rebuilds now, and the page
> rebuilds by itself once it is over 60 min old. See *Streamlit app* below.

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
| `streamlit_app.py`, `Stocks Picking app.bat`, `.streamlit/config.toml` | The Streamlit app (port 8502, dark theme). |

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
| Units sold per product per day, per market | Odoo POS: `self_made_combos._bag_sales_daily_sql` / `BAG_SALES_DAILY_SINZA_SQL` / `_UGANDA_` (combo wrappers `+`, delivery, customisation, straps and gift bags are left out, as on Push Planner). **Kenya = the shop tills only**: the Website, Jumia and Staff POS tills are left out (`KENYA_NON_SHOP_TILLS`, plus any till named like "website"). |
| Live stock per product, per market | `lib/stock.odoo_stock_by_shop_code(codes)`, summed over the shops: shop stock only. **Kenya = all 18 Kenya shops** (lib/stock's 16 shop codes + `EXTRA_KENYA_SHOPS` Machakos, Nyeri); never the Website (WEB), CBD, Validation (VLD) or any other warehouse. Sinza = DAR, Uganda = UG. The Stock rate's stock moves use the same shops. |
| Bag type | `self_made_combos.bag_classifier()` |
| Colour | `lib/colours.family()`: shades fold into families (Chocolate / Spice / Antelope → Brown, Nude → Beige, CN / TT / 018 → base colour) |
| Category | `bag_tiers.csv`, else the bag's most common `bag_names.csv` category, else OTHER |

**Left out:** gift bags, and `[REJECT]` products (the dashboard's Reject Sale page covers them).

A bag the price catalogue doesn't know yet (e.g. LAFEMME) still shows if `bag_names.csv` lists it, or lists another
colour of it. Everything else (wipes, cleaners, laptop sleeves, promo items) is counted as "not a bag" in the build log.

## Periods and offer (one choice for the whole page)

The **Period** dropdown and the **Offer** chips at the top drive every section (KPIs, Colour mix, Colours to act on,
Colour comparison by bag, Stock rate). Periods are the Marketing dashboard's (Bags on offer): **Monthly** = the live
month to date, **Weekly** = this Sun–Sat week to date, **Last week** (default) = the last full Sun–Sat week,
**Custom** = any From–To inside the data window (120 days). Units sold for any period come from the daily series in the
page, so switching needs no rebuild. Stock is always live (now); **Days cover** and the **Restock** signal keep using
the last 28 days' pace. **Push** = ≥ 90 % redundant in the chosen period, so a short period (Weekly early in the week)
flags more colours. **Offer**: All / On offer / Not on offer, or one offer type from a table's Offer box; the
act-on lists show each bag's offer tags. Remembered per browser (`spr-state`).

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

## Marketing Bags For Shoot — Stock rate (the first section on the page)

**Sold rate** = units sold in the period ÷ the shop stock there on the **morning of its first day**, per colour,
bag (totals, not an average), category and market, beside **Stock now** (live) and the bag's **offer** status.

| Column | Meaning |
|---|---|
| **Stock at start** | stock now − the net done stock moves in/out of the market's shops from the first day to now (`MOVES_SQL`; moves between two of its shops cancel). A rebuild below 0 counts as 0. |
| **Received** | units moved into the shops during the period from anywhere but a customer (deliveries, transfers) |
| **Sold** | POS units in the period (same query as the rest of the page, up to today) |
| **Sold rate** | sold ÷ stock at start; over 100 % = received stock sold too; "new stock" = nothing there on day 1 but it sold |
| **Stock rate** | stock now ÷ stock at start: how much of the stock the period started with is still there (below 100 % = it went down; above 100 % = more came in than went out, shown green); "new stock" = nothing there on day 1. Bag / category rows use their totals. |
| **Signal** | **Push #1–3** on a colour row = **each bag's** 3 colours with the most stock now (`PUSH_TOP`; fewer when a bag has fewer colours in stock), e.g. Code 3 (12 Oct 2026): Green #1 (88), Grey #2 (75), Brown #3 (64). Filter it (Any / Push / None: keeps the matching colours and their bags) or sort by it. |
| **Offer** | from the Marketing dashboard, for the month the period ends in. Kenya: `bags_offer_source.json` / `bags_offer_source_<YYYY-MM>.json` `onOffer` (Power Deal, Deal of the Week, Combo = combo component), matched with `bag_classifier`. Sinza / Uganda: `offers_monthly.csv` (Combo, Single offer). Plus this month's new products (`BOO.newProducts` in `bags_on_offer.html`). No tag = **Not on offer**. If the dashboard has no list for that month, the latest earlier one is used and the page says so. |

**Periods**: the page's Period dropdown (see *Periods and offer*). The
page ships `DAILY_DAYS` = 120 days of daily sold / net moves / received per colour (`s`, `n`, `r` by day index from
`CC.day0`), so every period is worked out in the browser. Table sort / filters remembered per browser (`spr-rate`).

Reverse check (Kenya, last week 4–10 Oct 2026): BABY BAG Brown 28 at start + 4 received − 3 sold = 29 now; Kenya
10,295 at start, 3,496 sold → 34.0 % (on offer 38.3 %, not on offer 17.9 %). Since the Kenya = shops-only
change (12 Oct 2026, Website / Jumia / Staff POS sales out, Machakos + Nyeri in): 10,296 at start, 3,228 sold → 31.4 %.

## Page

1. **KPI tiles:** stock in shops, units sold, the market's redundancy rate (all stock, plus the average of bags), the
   least and most redundant colour family, and the colours to act on.
2. **Colour mix:** each colour family's share of stock beside its share of sales, with a table of redundancy, sold,
   stock and the gap (sortable, with a filter row).
3. **Colours to act on:** Restock (lowest cover first) and Push (most stock first), 15 each.
4. **Colour comparison by bag:** the grouped table with an **Offer** column and category chips. Every column sorts
   (click its name) and filters from the row under the names: text, Offer, number boxes (Redundancy and the mixes in %,
   Days cover in days) and **Signal** (To act on / Restock / Push / Best colour / No signal). **Bags** tests each bag's
   row (the mixes and the signal: one of its colours) and keeps all its colours; **Colours** keeps only the colours that
   pass. Hover a colour to see the Odoo products folded into it.

5. **Marketing Bags For Shoot (Stock rate)** (shown first, right under the KPI tiles): see above. Every column is sortable (click its name; again to reverse) and filterable from the row
   under the headers: Bag / colour (text), Offer (All, On offer, Not on offer or one tag, also the chips above), and
   the number columns (`>50`, `<10`, `>=5`, `=0`, `10-50`, or a plain number = at least; Sold rate and Stock rate in %; an invalid
   entry turns red and is ignored). **Filter: Bags** tests each bag's totals and keeps all its colours; **Colours**
   tests each colour and keeps only those that pass (the bag shows "2 of 5 colours"). Clear filters resets them.
   Sort, filters and the Bags / Colours choice are remembered in `spr-rate`.

Big tables keep their filter bar, column names and filter boxes in view while scrolling (inside the Streamlit apps
they scroll in their own window-tall box). The chosen market, period, offer and filters are remembered in the browser
(`localStorage` keys `spr-state`, `spr-rate`).

## Streamlit app

`streamlit_app.py` shows `colour_comparison.html` and keeps it fresh, the same way the Marketing dashboard's app does:

- **Refresh** (top right) runs `colour_comparison.py` with `DENRI_FORCE_FRESH=1` (skips the Odoo cache). About 30–40 s.
- **Auto-refresh:** when the page is over `AUTO_REFRESH_MIN` = 60 min old, it rebuilds on the next view, and an open
  tab checks every minute. An auto rebuild is tried at most once per hour, so a failing build doesn't loop.
- A rebuild runs in the background, one at a time for all viewers. A progress bar shows it, the last build stays on
  screen, and the new page swaps in when it's done. A failed build shows its log and keeps the old page.
- `page_sidebar.js` / `chart_switcher.js` are inlined into the frame; the frame sizes itself to the page.
- `SPR_NO_AUTOREFRESH=1` turns auto-refresh off (testing).
- It needs the Marketing dashboard folder next to this one (Odoo connection and `lib/`), so it runs on this PC.
  Putting it on Streamlit Cloud would need this folder in a GitHub repo together with the dashboard's `lib/`.

The dashboard also has a copy as its Marketing › Stocks Picking menu (`stocks_picking.py`, not published yet).

