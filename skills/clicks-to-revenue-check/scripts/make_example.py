#!/usr/bin/env python
"""make_example.py: build the synthetic September 2026 clicks-to-revenue pack with three planted gaps.

Writes to references/example/: shopify_orders.csv, report.csv (the platforms' revenue by campaign),
matching_rules.json. Deterministic: starts at seed 20261010 and steps up until every planted gap clears the
tolerance (abs 1.00 or 0.01% of source) and the rounding gap stays within half a unit per order.

Planted (page = the platform's claim; source = the store's orders):
  1. timing     Meta Retargeting's claim includes 23 orders the store dates 2026-10-01 (inside a 7-day click window).
  2. duplicate  The store export carries 4 Google Shopping orders twice (an overlapping re-export); the platform counts each once.
  3. rounding   Google Brand reports each order's value rounded to whole dollars.
Meta Prospecting and Google Performance Max tie. "Total attributed" is the sum of the four, consistent on the page.
Unattributed orders (no UTMs) exist in the store and are on no platform's page.
"""
import csv
import datetime as dt
import json
import os
import random
from decimal import Decimal, ROUND_HALF_UP

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "references", "example")
CENT = Decimal("0.01")

CAMPAIGNS = [("meta", "prospecting", "Meta: Prospecting"), ("meta", "retargeting", "Meta: Retargeting"),
             ("google", "brand", "Google: Brand"), ("google", "shopping", "Google: Shopping"),
             ("google", "pmax", "Google: Performance Max")]


def q(v):
    return Decimal(v).quantize(CENT, rounding=ROUND_HALF_UP)


def build(seed):
    rng = random.Random(seed)
    start, end = dt.date(2026, 9, 1), dt.date(2026, 9, 30)
    orders, oid = [], [50000]

    def order(date, src, camp, total):
        oid[0] += 1
        o = {"order_id": f"#{oid[0]}", "order_date": date.isoformat(), "utm_source": src, "utm_campaign": camp,
             "total": str(q(total))}
        orders.append(o)
        return o

    per_day = {"prospecting": (3, 7), "retargeting": (2, 5), "brand": (4, 8), "shopping": (3, 6), "pmax": (2, 4)}
    for i in range(30):
        d = start + dt.timedelta(days=i)
        for src, camp, _ in CAMPAIGNS:
            for _ in range(rng.randint(*per_day[camp])):
                order(d, src, camp, Decimal(rng.uniform(45, 260)))
        for _ in range(rng.randint(2, 5)):
            order(d, "", "", Decimal(rng.uniform(45, 260)))
    # late-August and early-October noise on every campaign (counted by neither side)
    for d in (dt.date(2026, 8, 30), dt.date(2026, 8, 31), dt.date(2026, 10, 2), dt.date(2026, 10, 3)):
        for src, camp, _ in CAMPAIGNS:
            for _ in range(rng.randint(1, 3)):
                order(d, src, camp, Decimal(rng.uniform(45, 260)))
    # planted 1: 23 retargeting orders dated Oct 1 that Meta attributes to September clicks
    oct1 = [order(dt.date(2026, 10, 1), "meta", "retargeting", Decimal(rng.uniform(45, 260))) for _ in range(23)]
    # planted 2: four Google Shopping September orders exported twice
    shop_sep = [o for o in orders if o["utm_campaign"] == "shopping" and start <= dt.date.fromisoformat(o["order_date"]) <= end]
    dups = rng.sample(shop_sep, 4)
    for o in dups:
        orders.append(dict(o))

    def tot(rows):
        return sum(Decimal(r["total"]) for r in rows)

    def sep(camp):
        return [o for o in orders if o["utm_campaign"] == camp and start <= dt.date.fromisoformat(o["order_date"]) <= end]

    store = {camp: tot(sep(camp)) for _, camp, _ in CAMPAIGNS}          # as the store file actually sums (dups in)
    page = {}
    page["prospecting"] = store["prospecting"]
    page["retargeting"] = store["retargeting"] + tot(oct1)
    # planted 3: Google Brand rounds each order to whole dollars
    page["brand"] = sum(Decimal(o["total"]).quantize(Decimal("1"), rounding=ROUND_HALF_UP) for o in sep("brand"))
    page["shopping"] = store["shopping"] - tot(dups)
    page["pmax"] = store["pmax"]
    total_page = sum(page.values())

    def tol(x):
        return max(Decimal("1.00"), Decimal("0.0001") * abs(x))
    gaps = {"timing": page["retargeting"] - store["retargeting"], "duplicate": page["shopping"] - store["shopping"],
            "rounding": page["brand"] - store["brand"]}
    for k, g in gaps.items():
        base = {"timing": store["retargeting"], "duplicate": store["shopping"], "rounding": store["brand"]}[k]
        if abs(g) <= tol(base):
            return None
    if abs(gaps["rounding"]) > Decimal("0.5") * len(sep("brand")):
        return None
    report = [(label, page[camp]) for _, camp, label in CAMPAIGNS] + [("Total attributed", total_page)]
    return orders, report, gaps


def main():
    os.makedirs(OUT, exist_ok=True)
    seed, built = 20261010, None
    while built is None:
        built = build(seed)
        if built is None:
            seed += 1
    orders, report, gaps = built
    with open(os.path.join(OUT, "shopify_orders.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["order_id", "order_date", "utm_source", "utm_campaign", "total"])
        w.writeheader()
        for o in sorted(orders, key=lambda o: (o["order_date"], o["order_id"])):
            w.writerow(o)
    with open(os.path.join(OUT, "report.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["figure", "value"])
        for name, v in report:
            w.writerow([name, str(q(v))])
    rules = {
        "title": "Synthetic September 2026 store: platform-reported revenue vs Shopify orders (example, not a client)",
        "period": {"start": "2026-09-01", "end": "2026-09-30"},
        "tolerance": {"abs": "1.00", "pct": "0.0001"},
        "timing_window_days": 7,
        "sources": {"store": {"path": "shopify_orders.csv", "date_col": "order_date", "amount_col": "total", "id_col": "order_id"}},
        "figures": [
            {"figure": label, "source": "store", "filter": {"utm_source": [src], "utm_campaign": [camp]}}
            for src, camp, label in CAMPAIGNS
        ] + [{"figure": "Total attributed", "derived": " + ".join(label for _, _, label in CAMPAIGNS)}]
    }
    with open(os.path.join(OUT, "matching_rules.json"), "w", encoding="utf-8") as f:
        json.dump(rules, f, indent=2)
    print(f"wrote example pack to {os.path.abspath(OUT)}: {len(orders)} order rows, {len(report)} figures (seed {seed})")
    print("planted gaps (platform minus store): " + ", ".join(f"{k} {q(v)}" for k, v in gaps.items()))


if __name__ == "__main__":
    main()
