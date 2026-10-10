#!/usr/bin/env python
"""tie_out.py: tie a report's figures back to their sources and say what differs.

Usage:
    python tie_out.py --report report.csv --rules matching_rules.json --out <dir>

Writes to <dir>: tie_out_note.md, differences.csv, checks.txt, and appends one line to run_log.csv.

Exit codes:
    0  every figure had a rule and every source loaded
    1  the note was written, but a figure had no rule or a source had no usable rows (the note names it)
    2  inputs unreadable or malformed; nothing written

Standard library only. Never changes an input. Never picks a winner.
"""
import argparse
import csv
import datetime as dt
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def die(msg):
    sys.stderr.write("tie_out: " + msg + "\n")
    sys.exit(2)


def money(s):
    """Parse '1,234.50', '$1,234.50', '(1,234.50)', '-1234.5'. Blank -> None. Garbage -> raises."""
    if s is None:
        return None
    t = str(s).strip()
    if t == "":
        return None
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()").replace("$", "").replace(",", "").strip()
    v = Decimal(t)
    return -v if neg else v


def q(v):
    return v.quantize(CENT, rounding=ROUND_HALF_UP)


def fmt(v, agg="sum"):
    if v is None:
        return "n/a"
    if agg == "count":
        return str(int(v))
    s = f"{q(abs(v)):,.2f}"
    return f"({s})" if v < 0 else s


def parse_date(s):
    t = str(s).strip()
    for f in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(t, f).date()
        except ValueError:
            pass
    return None


def load_report(path):
    if not os.path.exists(path):
        die(f"report not found: {path}")
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        if not r.fieldnames or [c.strip().lower() for c in r.fieldnames[:2]] != ["figure", "value"]:
            die(f"report must have columns figure,value; got {r.fieldnames}")
        for i, row in enumerate(r, start=2):
            fig = (row.get("figure") or "").strip()
            if not fig:
                die(f"report row {i}: blank figure name")
            try:
                val = money(row.get("value"))
            except InvalidOperation:
                die(f"report row {i}: value {row.get('value')!r} is not a number")
            if val is None:
                die(f"report row {i}: figure {fig!r} has a blank value")
            rows.append((fig, val))
    names = [f for f, _ in rows]
    dup = [n for n, c in Counter(names).items() if c > 1]
    if dup:
        die(f"report lists a figure more than once: {dup}")
    if not rows:
        die("report has no figures")
    return rows


def load_rules(path):
    if not os.path.exists(path):
        die(f"rules not found: {path}")
    with open(path, encoding="utf-8") as f:
        try:
            rules = json.load(f)
        except json.JSONDecodeError as e:
            die(f"rules not valid JSON: {e}")
    for k in ("period", "sources", "figures"):
        if k not in rules:
            die(f"rules missing key {k!r}")
    p = rules["period"]
    start, end = parse_date(p.get("start", "")), parse_date(p.get("end", ""))
    if not start or not end or start > end:
        die("rules.period needs start and end dates, start <= end")
    tol = rules.get("tolerance", {})
    rules["_tol_abs"] = Decimal(str(tol.get("abs", "1.00")))
    rules["_tol_pct"] = Decimal(str(tol.get("pct", "0.001")))
    rules["_start"], rules["_end"] = start, end
    rules["_window"] = int(rules.get("timing_window_days", 5))
    return rules


def load_source(name, spec, base):
    path = os.path.join(base, spec["path"])
    if not os.path.exists(path):
        die(f"source {name!r}: file not found: {path}")
    date_col, amt_col, id_col = spec.get("date_col"), spec.get("amount_col"), spec.get("id_col")
    rows, counts = [], Counter()
    with open(path, newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        if r.fieldnames is None:
            die(f"source {name!r}: empty file")
        for col in (date_col, amt_col, id_col):
            if col and col not in r.fieldnames:
                die(f"source {name!r}: column {col!r} not in {r.fieldnames}")
        for i, row in enumerate(r, start=2):
            counts["rows_read"] += 1
            rec = {"_line": i, "_raw": {k: (v or "").strip() for k, v in row.items()}}
            if date_col:
                d = parse_date(row[date_col])
                if d is None:
                    counts["unparsable_date"] += 1
                rec["_date"] = d
            if amt_col:
                try:
                    a = money(row[amt_col])
                except InvalidOperation:
                    die(f"source {name!r} line {i}: amount {row[amt_col]!r} is not a number")
                if a is None:
                    counts["blank_amount"] += 1
                rec["_amount"] = a
            if id_col:
                rec["_id"] = (row[id_col] or "").strip()
            rows.append(rec)
    if counts["rows_read"] == 0:
        counts["empty"] = 1
    return {"name": name, "spec": spec, "rows": rows, "counts": counts}


def in_period(rec, rules):
    d = rec.get("_date")
    return d is not None and rules["_start"] <= d <= rules["_end"]


def matches(rec, flt):
    for col, allowed in (flt or {}).items():
        if rec["_raw"].get(col) not in [str(a).strip() for a in allowed]:
            return False
    return True


def tolerance_for(source_total, rules):
    base = abs(source_total) if source_total is not None else Decimal(0)
    return max(rules["_tol_abs"], (rules["_tol_pct"] * base))


def source_total(rule, src, rules):
    """Return (total, matched_in_period_rows, matched_out_of_period_rows)."""
    agg = rule.get("agg", "sum")
    sign = Decimal(str(rule.get("sign", 1)))
    has_date = bool(src["spec"].get("date_col"))
    inside, outside = [], []
    for rec in src["rows"]:
        if not matches(rec, rule.get("filter")):
            continue
        if has_date and not in_period(rec, rules):
            outside.append(rec)
        else:
            inside.append(rec)
    if agg == "count":
        return sign * Decimal(len(inside)), inside, outside
    if not src["spec"].get("amount_col"):
        die(f"figure {rule['figure']!r}: source {src['name']!r} has no amount_col but agg is sum")
    total = sum((r["_amount"] for r in inside if r["_amount"] is not None), Decimal(0))
    return sign * total, inside, outside


DERIVED_RE = re.compile(r"\s([+-])\s")


def parse_derived(expr):
    parts = DERIVED_RE.split(expr.strip())
    terms, sign = [], 1
    for i, p in enumerate(parts):
        if i % 2 == 1:
            sign = 1 if p == "+" else -1
        else:
            terms.append((sign, p.strip()))
    return terms


def eval_derived(terms, values):
    total = Decimal(0)
    for s, name in terms:
        if name not in values or values[name] is None:
            return None
        total += s * values[name]
    return total


def approx(a, b, tol):
    return a is not None and b is not None and abs(a - b) <= tol


def diagnose(fig, rule, gap, inside, outside, src, rules, tol):
    """Return (cause, detail, all_tests) by rule, in fixed order."""
    tests = []
    sign = Decimal(str(rule.get("sign", 1)))
    agg = rule.get("agg", "sum")
    # 1. timing
    if outside and agg == "sum":
        w = rules["_window"]
        lo, hi = rules["_start"] - dt.timedelta(days=w), rules["_end"] + dt.timedelta(days=w)
        win = [r for r in outside if r["_date"] and lo <= r["_date"] <= hi and r["_amount"] is not None]
        by_date = defaultdict(list)
        for r in win:
            by_date[r["_date"]].append(r)
        groups = []
        for d in sorted(by_date):
            groups.append((f"rows dated {d}", by_date[d]))
        before = [r for r in win if r["_date"] < rules["_start"]]
        after = [r for r in win if r["_date"] > rules["_end"]]
        if before:
            groups.append((f"all rows before the period within {w} days", before))
        if after:
            groups.append((f"all rows after the period within {w} days", after))
        if win:
            groups.append((f"all rows within {w} days outside the period", win))
        hit = None
        for label, rs in groups:
            tot = sign * sum(r["_amount"] for r in rs)
            ok = approx(tot, gap, tol)
            tests.append(("timing", f"{label}: {len(rs)} rows sum to {fmt(tot)}", ok))
            if ok and hit is None:
                hit = (label, rs, tot)
        if hit:
            label, rs, tot = hit
            return ("timing", f"{len(rs)} {label} sum to {fmt(tot)}, which is the gap. The report counts them; "
                              f"the source dates them outside {rules['_start']} to {rules['_end']}.", tests)
    else:
        tests.append(("timing", "no rows outside the period match this figure", False))
    # 2. duplicate
    if src["spec"].get("id_col") and agg == "sum":
        ids = Counter(r["_id"] for r in inside if r["_id"])
        dups = {i: c for i, c in ids.items() if c > 1}
        hit = None
        for i, c in sorted(dups.items()):
            amts = [r["_amount"] for r in inside if r["_id"] == i and r["_amount"] is not None]
            extra = sign * sum(amts[1:], Decimal(0))
            ok = approx(extra, -gap, tol) or approx(extra, gap, tol)
            tests.append(("duplicate", f"id {i} appears {c} times; extra {fmt(extra)}", ok))
            if ok and hit is None:
                hit = (i, c, extra)
        if not dups:
            tests.append(("duplicate", "no id appears more than once in the period", False))
        if hit:
            i, c, extra = hit
            side = "the source carries it and the report does not" if approx(extra, -gap, tol) else \
                   "the report carries it and the source does not"
            return ("duplicate", f"id {i} appears {c} times in the source with the same amount; the extra "
                                 f"{fmt(abs(extra))} is the gap, so {side}.", tests)
        if len(dups) > 1:
            total_extra = Decimal(0)
            for i in dups:
                amts = [r["_amount"] for r in inside if r["_id"] == i and r["_amount"] is not None]
                total_extra += sign * sum(amts[1:], Decimal(0))
            ok = approx(total_extra, -gap, tol) or approx(total_extra, gap, tol)
            tests.append(("duplicate", f"all {len(dups)} duplicated ids together; extra {fmt(total_extra)}", ok))
            if ok:
                side = "the source carries them and the report does not" if approx(total_extra, -gap, tol) else \
                       "the report carries them and the source does not"
                ids = ", ".join(sorted(dups)[:6]) + (" ..." if len(dups) > 6 else "")
                return ("duplicate", f"{len(dups)} ids appear more than once in the source ({ids}); their extra "
                                     f"amounts together are {fmt(abs(total_extra))}, the gap, so {side}.", tests)
    else:
        tests.append(("duplicate", "source has no id column; duplicate check skipped", False))
    # 3. rounding scale
    n = len(inside)
    if n and agg == "sum":
        bound = Decimal("0.5") * n
        ok = abs(gap) <= bound
        tests.append(("rounding-scale", f"gap {fmt(gap)} vs half a unit per row ({n} rows = {fmt(bound)})", ok))
        if ok:
            return ("rounding-scale", f"the gap of {fmt(gap)} is within half a unit per line over {n} lines, the "
                                      f"size rounding would make. That is a size test, not a proof.", tests)
    return ("unexplained", "no detector matched. The rows are listed in checks.txt.", tests)


def git_commit():
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


NOTE_TAIL = """## What this cannot tell you

Which side is right. A tie-out shows where the report and its source disagree and how big the gap is. It does not
know which date basis your board expects, whether a duplicated journal was meant to be reversed, or what rounding
rule your pack is supposed to follow. Those are rules someone set once, usually by habit, and they live in your
close process, not in the files. Finding each one, writing it down, and testing it against your own history is the
next piece of work, and sometimes the honest answer is that the rule you have is fine.

Nothing in the report or the sources was changed by this run.
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", required=True)
    ap.add_argument("--rules", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    report = load_report(args.report)
    rules = load_rules(args.rules)
    base = os.path.dirname(os.path.abspath(args.rules))
    sources = {name: load_source(name, spec, base) for name, spec in rules["sources"].items()}
    if not os.path.isdir(args.out):
        die(f"out dir does not exist: {args.out}")

    rule_by_fig = {}
    for r in rules["figures"]:
        if "figure" not in r:
            die(f"a rule has no 'figure': {r}")
        if r["figure"] in rule_by_fig:
            die(f"two rules for figure {r['figure']!r}")
        rule_by_fig[r["figure"]] = r

    report_vals = dict(report)
    results = []        # one dict per report figure, in page order
    src_vals = {}       # figure -> source-side total
    detail = {}         # figure -> (inside, outside, src)
    exit_code = 0

    # pass 1: direct figures
    for fig, rv in report:
        rule = rule_by_fig.get(fig)
        if rule is None or "derived" in rule:
            continue
        src = sources.get(rule.get("source"))
        if src is None:
            die(f"figure {fig!r}: source {rule.get('source')!r} not in rules.sources")
        total, inside, outside = source_total(rule, src, rules)
        src_vals[fig] = total
        detail[fig] = (inside, outside, src)
    # pass 2: derived (two sweeps so derived-of-derived resolves)
    for _ in range(2):
        for fig, rv in report:
            rule = rule_by_fig.get(fig)
            if rule and "derived" in rule and fig not in src_vals:
                v = eval_derived(parse_derived(rule["derived"]), src_vals)
                if v is not None:
                    src_vals[fig] = v

    for fig, rv in report:
        rule = rule_by_fig.get(fig)
        row = {"figure": fig, "report": rv, "source": None, "gap": None, "gap_pct": "", "status": "",
               "cause": "", "detail": "", "tests": [], "agg": (rule or {}).get("agg", "sum")}
        if rule is None:
            row["status"], row["cause"] = "NO RULE", "no matching rule for this figure"
            exit_code = 1
            results.append(row)
            continue
        sv = src_vals.get(fig)
        if sv is None:
            row["status"], row["cause"] = "NO SOURCE ROWS", "the derived formula references a figure with no value"
            exit_code = 1
            results.append(row)
            continue
        if "derived" not in rule and not detail[fig][0]:
            row["status"], row["cause"] = "NO SOURCE ROWS", "no source rows matched the filter in the period"
            row["source"] = sv
            exit_code = 1
            results.append(row)
            continue
        row["source"] = sv
        gap = rv - sv
        row["gap"] = gap
        row["gap_pct"] = f"{(abs(gap) / abs(sv) * 100):.2f}%" if sv else ""
        tol = tolerance_for(sv, rules)
        if abs(gap) <= tol:
            row["status"] = "TIES"
            results.append(row)
            continue
        row["status"] = "DIFFERS"
        if "derived" in rule:
            terms = parse_derived(rule["derived"])
            page_side = eval_derived(terms, report_vals)
            comps = [n for _, n in terms]
            bad = [n for n in comps if any(r["figure"] == n and r["status"] == "DIFFERS" for r in results)]
            if page_side is not None and not approx(page_side, rv, tol):
                row["cause"] = "page-arithmetic"
                row["detail"] = (f"the page's own components ({rule['derived']}) give {fmt(page_side)}, but the page "
                                 f"prints {fmt(rv)}.")
            elif bad:
                row["cause"] = "carried"
                row["detail"] = f"inherits the gap in {', '.join(bad)}; nothing new at this line."
            else:
                row["cause"] = "unexplained"
                row["detail"] = "components tie and the page arithmetic holds, yet the figure differs; check the formula in the rules."
            results.append(row)
            continue
        inside, outside, src = detail[fig]
        cause, dtl, tests = diagnose(fig, rule, gap, inside, outside, src, rules, tol)
        row["cause"], row["detail"], row["tests"] = cause, dtl, tests
        results.append(row)

    n = len(results)
    ties = sum(1 for r in results if r["status"] == "TIES")
    differs = [r for r in results if r["status"] == "DIFFERS"]
    root = [r for r in differs if r["cause"] != "carried"]
    carried = [r for r in differs if r["cause"] == "carried"]
    missing = [r for r in results if r["status"] in ("NO RULE", "NO SOURCE ROWS")]
    now = dt.datetime.now().replace(microsecond=0).isoformat(sep=" ")
    title = rules.get("title", "Tie-out")

    # differences.csv
    with open(os.path.join(args.out, "differences.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["figure", "report", "source", "gap", "gap_pct", "status", "cause", "detail"])
        for r in results:
            w.writerow([r["figure"], fmt(r["report"], r["agg"]), fmt(r["source"], r["agg"]),
                        fmt(r["gap"], r["agg"]), r["gap_pct"], r["status"], r["cause"], r["detail"]])

    # checks.txt (technical surface)
    lines = [f"# checks: {title}", f"run: {now}", f"period: {rules['_start']} to {rules['_end']}",
             f"tolerance: abs {rules['_tol_abs']} or pct {rules['_tol_pct']} of source, whichever is larger",
             f"timing window: {rules['_window']} days", ""]
    lines.append("## sources: counts in")
    for name, src in sources.items():
        c = src["counts"]
        has_date = bool(src["spec"].get("date_col"))
        inp = sum(1 for r in src["rows"] if (not has_date) or in_period(r, rules))
        lines.append(f"- {name} ({src['spec']['path']}): rows read {c['rows_read']}, in period {inp}, "
                     f"outside period {c['rows_read'] - inp}, blank amount {c['blank_amount']}, "
                     f"unparsable date {c['unparsable_date']}")
        if src["spec"].get("id_col"):
            ids = Counter(r["_id"] for r in src["rows"] if r.get("_id"))
            d = sorted(i for i, k in ids.items() if k > 1)
            lines.append(f"  duplicate ids in file: {len(d)}" + (f" ({', '.join(d[:10])})" if d else ""))
    lines.append("")
    lines.append("## figures: rows matched, totals, verdict")
    for r in results:
        rule = rule_by_fig.get(r["figure"], {})
        if "derived" in rule:
            how = f"derived: {rule['derived']}"
        elif rule:
            how = f"{rule.get('source')} where {json.dumps(rule.get('filter', {}))} sign {rule.get('sign', 1)} agg {rule.get('agg', 'sum')}"
            if r["figure"] in detail:
                inside, outside, _ = detail[r["figure"]]
                how += f"; matched {len(inside)} in period, {len(outside)} outside"
        else:
            how = "no rule"
        lines.append(f"- {r['figure']}: report {fmt(r['report'], r['agg'])} | source {fmt(r['source'], r['agg'])} | "
                     f"gap {fmt(r['gap'], r['agg'])} | {r['status']}" + (f" ({r['cause']})" if r["cause"] else ""))
        lines.append(f"    {how}")
        for kind, what, ok in r["tests"]:
            lines.append(f"    test {kind}: {what} -> {'MATCH' if ok else 'no'}")
    lines.append("")
    lines.append(f"## counts out: {n} figures, {ties} tie, {len(root)} differ at source, {len(carried)} carried, "
                 f"{len(missing)} without a rule or rows")
    lines.append(f"exit code: {exit_code}")
    with open(os.path.join(args.out, "checks.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    # tie_out_note.md (plain surface)
    note = [f"# Tie-out: {title}", "",
            f"*Run {now}. Period {rules['_start']} to {rules['_end']}. Sources: " +
            ", ".join(f"{k} ({v['spec']['path']})" for k, v in sources.items()) +
            f". A figure ties when the gap is within ${rules['_tol_abs']} or {rules['_tol_pct'] * 100}% of the source.*", ""]
    head = f"**{ties} of {n} figures tie to source.**"
    if root:
        head += f" {len(root)} differ at source"
        if carried:
            head += f", and {len(carried)} derived figure{'s' if len(carried) > 1 else ''} carr{'y' if len(carried) > 1 else 'ies'} those gaps"
        head += "."
    if missing:
        head += f" {len(missing)} could not be checked (listed below)."
    note += [head, "", "| Figure | Report | Source | Gap | Reading |", "|---|---|---|---|---|"]
    for r in results:
        reading = {"TIES": "ties", "DIFFERS": r["cause"], "NO RULE": "no rule: not checked",
                   "NO SOURCE ROWS": "no source rows: not checked"}[r["status"]]
        note.append(f"| {r['figure']} | {fmt(r['report'], r['agg'])} | {fmt(r['source'], r['agg'])} | "
                    f"{fmt(r['gap'], r['agg'])} | {reading} |")
    note.append("")
    if root or missing or carried:
        note.append("## The differences, one at a time")
        note.append("")
        for r in root:
            note.append(f"- **{r['figure']}**, gap {fmt(r['gap'], r['agg'])}" +
                        (f" ({r['gap_pct']})" if r["gap_pct"] else "") + f". {r['cause']}: {r['detail']}")
        for r in carried:
            note.append(f"- **{r['figure']}**: {r['detail']}")
        for r in missing:
            note.append(f"- **{r['figure']}**: {r['cause']}. Add the rule and re-run.")
        note.append("")
    note.append("## Checks run")
    note.append("")
    for name, src in sources.items():
        has_date = bool(src["spec"].get("date_col"))
        inp = sum(1 for r in src["rows"] if (not has_date) or in_period(r, rules))
        note.append(f"- {name}: {src['counts']['rows_read']} rows read, {inp} in the period, "
                    f"{src['counts']['rows_read'] - inp} outside it.")
    note.append(f"- Every figure on the page was given a verdict: {ties} tie, {len(differs)} differ, {len(missing)} not checked.")
    note.append("- Each gap was tested, in order, for timing, a duplicated id, and rounding scale; derived figures for page arithmetic. Details in checks.txt.")
    note.append("")
    note.append(NOTE_TAIL)
    with open(os.path.join(args.out, "tie_out_note.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(note))

    # run_log.csv
    logp = os.path.join(args.out, "run_log.csv")
    new = not os.path.exists(logp)
    with open(logp, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["run", "commit", "report", "rules", "figures", "tie", "differ_at_source", "carried", "unchecked", "exit"])
        w.writerow([now, git_commit(), os.path.basename(args.report), os.path.basename(args.rules), n, ties,
                    len(root), len(carried), len(missing), exit_code])

    print(head)
    print(f"wrote tie_out_note.md, differences.csv, checks.txt in {args.out}; exit {exit_code}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
