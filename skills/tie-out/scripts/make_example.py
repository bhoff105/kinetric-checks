#!/usr/bin/env python
"""make_example.py: build the synthetic September 2026 month-end pack with three planted differences.

Writes to references/example/: gl_extract.csv, hris_extract.csv, report.csv, matching_rules.json.
Deterministic: starts at seed 20261010 and steps up until every planted gap clears the example tolerance
(abs 1.00 or 0.01% of source) and the rounding gap stays within half a unit per line; prints the seed used.

Planted:
  1. timing     Revenue on the page includes 31 orders the GL dates 2026-10-01.
  2. rounding   COGS on the page was built from lines rounded to whole dollars.
  3. duplicate  Journal J-0318 (marketing) is posted twice in the GL; the page counts it once.
Everything else ties exactly, including the derived figures' page arithmetic.
"""
import csv
import datetime as dt
import json
import os
import random
import sys
from decimal import Decimal, ROUND_HALF_UP

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "references", "example")
CENT = Decimal("0.01")


def q(v):
    return Decimal(v).quantize(CENT, rounding=ROUND_HALF_UP)


def build(seed):
    rng = random.Random(seed)
    start, end = dt.date(2026, 9, 1), dt.date(2026, 9, 30)
    gl = []
    jid = [1000]

    def post(date, account, memo, amount):
        jid[0] += 1
        gl.append({"journal_id": f"J-{jid[0]:04d}", "date": date.isoformat(), "account": account,
                   "memo": memo, "amount": str(q(amount))})
        return gl[-1]

    # revenue: ~6 orders a day, credit-stored (negative), Sep 1-30, plus late-Aug and early-Oct noise
    def orders(d, n):
        for _ in range(n):
            post(d, rng.choice(["4000", "4010"]), "order", -Decimal(rng.uniform(120, 980)))
    for i in range(30):
        orders(start + dt.timedelta(days=i), rng.randint(4, 8))
    for d in (dt.date(2026, 8, 29), dt.date(2026, 8, 30), dt.date(2026, 8, 31)):
        orders(d, rng.randint(3, 6))
    # the planted timing group: 31 orders on Oct 1 that the page counts in September
    oct1 = []
    for _ in range(31):
        oct1.append(post(dt.date(2026, 10, 1), rng.choice(["4000", "4010"]), "order", -Decimal(rng.uniform(120, 980))))
    for d in (dt.date(2026, 10, 2), dt.date(2026, 10, 3)):
        orders(d, rng.randint(3, 6))

    # COGS: 4 lines a day in September, with cents
    cogs_lines = []
    for i in range(30):
        for _ in range(4):
            cogs_lines.append(post(start + dt.timedelta(days=i), "5000", "cost of goods", Decimal(rng.uniform(60, 420))))

    # opex
    payroll = [post(dt.date(2026, 9, 15), "6100", "payroll", Decimal("48250.00")),
               post(dt.date(2026, 9, 30), "6100", "payroll", Decimal("48250.00"))]
    rent = [post(dt.date(2026, 9, 1), "6200", "rent", Decimal("6400.00"))]
    mkt = [post(dt.date(2026, 9, 3), "6300", "ads: search", Decimal("5120.40")),
           post(dt.date(2026, 9, 12), "6300", "ads: social", Decimal("4250.00")),
           post(dt.date(2026, 9, 26), "6300", "agency fee", Decimal("3000.00"))]
    # planted duplicate: the Sep 12 social journal posted twice with the same id
    dup = dict(mkt[1])
    gl.append(dup)
    sw = [post(dt.date(2026, 9, 5), "6400", "software", Decimal("1890.00")),
          post(dt.date(2026, 9, 20), "6400", "software", Decimal("640.00"))]

    # truths on the GL side (September only, dedup'd as the GL actually is: the duplicate counts in the GL)
    def tot(rows):
        return sum(Decimal(r["amount"]) for r in rows)
    gl_sep = [r for r in gl if start <= dt.date.fromisoformat(r["date"]) <= end]
    rev_gl = -tot([r for r in gl_sep if r["account"] in ("4000", "4010")])
    cogs_gl = tot(cogs_lines)
    mkt_gl = tot([r for r in gl_sep if r["account"] == "6300"])

    # the page, with the three planted differences
    rev_page = rev_gl + (-tot(oct1))                                  # counts Oct 1 orders
    cogs_page = sum(Decimal(r["amount"]).quantize(Decimal("1"), rounding=ROUND_HALF_UP) for r in cogs_lines)
    mkt_page = mkt_gl - Decimal(dup["amount"])                        # counts the social journal once
    payroll_page, rent_page, sw_page = tot(payroll), tot(rent), tot(sw)
    gm_page = rev_page - cogs_page
    opex_page = payroll_page + rent_page + mkt_page + sw_page
    oi_page = gm_page - opex_page

    # headcount from an HRIS extract
    hris = []
    for i in range(1, 44):
        hris.append({"employee_id": f"E{i:03d}", "status": "active" if i <= 38 else "terminated"})
    hc_page = Decimal(38)

    report = [("Revenue", rev_page), ("COGS", cogs_page), ("Gross margin", gm_page), ("Payroll", payroll_page),
              ("Rent", rent_page), ("Marketing", mkt_page), ("Software", sw_page),
              ("Total operating expenses", opex_page), ("Operating income", oi_page), ("Headcount", hc_page)]

    # return None if a planted gap is inside the example tolerance (abs 1.00 or 0.01%)
    def tol(x):
        return max(Decimal("1.00"), Decimal("0.0001") * abs(x))
    gaps = {"timing": rev_page - rev_gl, "rounding": cogs_page - cogs_gl, "duplicate": mkt_page - mkt_gl}
    for k, g in gaps.items():
        base = {"timing": rev_gl, "rounding": cogs_gl, "duplicate": mkt_gl}[k]
        if abs(g) <= tol(base):
            return None
    if not (abs(gaps["rounding"]) <= Decimal("0.5") * len(cogs_lines)):
        return None
    return gl, hris, report, gaps


def main():
    os.makedirs(OUT, exist_ok=True)
    seed, built = 20261010, None
    while built is None:
        built = build(seed)
        if built is None:
            seed += 1
    gl, hris, report, gaps = built
    with open(os.path.join(OUT, "gl_extract.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["journal_id", "date", "account", "memo", "amount"])
        w.writeheader()
        for r in sorted(gl, key=lambda r: (r["date"], r["journal_id"])):
            w.writerow(r)
    with open(os.path.join(OUT, "hris_extract.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["employee_id", "status"])
        w.writeheader()
        w.writerows(hris)
    with open(os.path.join(OUT, "report.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["figure", "value"])
        for name, v in report:
            w.writerow([name, str(int(v)) if name == "Headcount" else str(q(v))])
    rules = {
        "title": "Synthetic September 2026 month-end pack (example, not a client)",
        "period": {"start": "2026-09-01", "end": "2026-09-30"},
        "tolerance": {"abs": "1.00", "pct": "0.0001"},
        "timing_window_days": 5,
        "sources": {
            "gl": {"path": "gl_extract.csv", "date_col": "date", "amount_col": "amount", "id_col": "journal_id"},
            "hris": {"path": "hris_extract.csv"}
        },
        "figures": [
            {"figure": "Revenue", "source": "gl", "filter": {"account": ["4000", "4010"]}, "sign": -1},
            {"figure": "COGS", "source": "gl", "filter": {"account": ["5000"]}},
            {"figure": "Gross margin", "derived": "Revenue - COGS"},
            {"figure": "Payroll", "source": "gl", "filter": {"account": ["6100"]}},
            {"figure": "Rent", "source": "gl", "filter": {"account": ["6200"]}},
            {"figure": "Marketing", "source": "gl", "filter": {"account": ["6300"]}},
            {"figure": "Software", "source": "gl", "filter": {"account": ["6400"]}},
            {"figure": "Total operating expenses", "derived": "Payroll + Rent + Marketing + Software"},
            {"figure": "Operating income", "derived": "Gross margin - Total operating expenses"},
            {"figure": "Headcount", "source": "hris", "agg": "count", "filter": {"status": ["active"]}}
        ]
    }
    with open(os.path.join(OUT, "matching_rules.json"), "w", encoding="utf-8") as f:
        json.dump(rules, f, indent=2)
    print(f"wrote example pack to {os.path.abspath(OUT)}: {len(gl)} GL rows, {len(hris)} HRIS rows, {len(report)} figures (seed {seed})")
    print("planted gaps (page minus GL): " + ", ".join(f"{k} {q(v)}" for k, v in gaps.items()))


if __name__ == "__main__":
    main()
