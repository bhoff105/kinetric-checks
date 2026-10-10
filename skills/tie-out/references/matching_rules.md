# matching_rules.json: what gets compared to what

The rules file is the technical surface. It says, for every figure on the report page, which source rows add up to
it. It never says which side is right.

## Schema

```json
{
  "title": "September 2026 month-end pack",
  "period": {"start": "2026-09-01", "end": "2026-09-30"},
  "tolerance": {"abs": "1.00", "pct": "0.001"},
  "timing_window_days": 5,
  "sources": {
    "gl":   {"path": "gl_extract.csv",  "date_col": "date", "amount_col": "amount", "id_col": "journal_id"},
    "hris": {"path": "hris_extract.csv"}
  },
  "figures": [
    {"figure": "Revenue",  "source": "gl", "filter": {"account": ["4000", "4010"]}, "sign": -1},
    {"figure": "COGS",     "source": "gl", "filter": {"account": ["5000"]}},
    {"figure": "Gross margin", "derived": "Revenue - COGS"},
    {"figure": "Headcount", "source": "hris", "agg": "count", "filter": {"status": ["active"]}}
  ]
}
```

| Key | Meaning |
|---|---|
| `period` | Inclusive dates. Rows outside it are counted and excluded, and used by the timing detector |
| `tolerance` | A figure ties when the gap is within `abs` or within `pct` of the source total, whichever is larger. Strings, so the decimals are exact |
| `timing_window_days` | How far outside the period the timing detector looks (default 5) |
| `sources.<name>.path` | CSV, relative to the rules file. `date_col`, `amount_col`, `id_col` are optional; a source with no `date_col` skips the period check; with no `id_col` skips the duplicate check |
| `figures[].filter` | Column name to list of allowed values, matched as trimmed strings. All keys must match |
| `figures[].sign` | Multiplies the source total. `-1` for credit-stored revenue. Default `1` |
| `figures[].agg` | `sum` (default, needs `amount_col`) or `count` |
| `figures[].derived` | An expression over other figure names with `+` and `-`, spaces around the operator. Evaluated on the source side and on the report side; both are compared |

## What the detectors do

For every figure that DIFFERS (gap = report minus source):

1. **Timing.** Among rows matching the filter but dated outside the period and within the window: does any single
   date's total, the before-period total, the after-period total, or the whole window equal the gap within
   tolerance? If yes: `timing`, with the dates and the row count.
2. **Duplicate.** Among in-period matching rows, ids that appear more than once: does the extra amount of any one
   duplicated id equal the gap (either sign) within tolerance? If not, do the extra amounts of all duplicated ids
   together equal it (a re-export that overlapped several rows)? If yes: `duplicate`, with the id or ids. Added
   2026-10-10 after the campaign-check test pack planted four double-exported orders and the per-id test missed
   them.
3. **Rounding scale.** Is the gap within half a unit per matching row? If yes: `rounding-scale`. This says the gap
   is the size rounding would make; it does not prove rounding caused it, and the note says that.
4. **Page arithmetic.** For a derived figure, the report's own components are combined by the same formula. If
   that disagrees with the report's printed figure: `page-arithmetic`.
5. **Carried.** For a derived figure whose components DIFFER: `carried`, naming the components.
6. Otherwise `unexplained`.

The first detector that fires is reported; the others are still printed in `checks.txt`.

## Editing it

Change the tolerance, the period, an account list or a sign, then re-run. The note's header prints the tolerance
and the period, so the owner always sees what was used. Don't add a rule that reads the report to decide the
source; that is bridging.
