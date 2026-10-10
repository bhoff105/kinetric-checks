---
name: tie-out
description: >-
  Tie a report's figures back to their sources before the report goes out: every number on the page is matched to
  a source total, every difference is listed with its size and its most likely cause (timing, duplicate, rounding,
  page arithmetic, or unexplained), and nothing is bridged silently. Use when Brendan or a client says "/tie-out",
  "tie this out", "do these numbers match the GL", "check the pack before it goes to the board", "reconcile the
  report to the source", or hands over a report plus one or more source extracts. Inputs: the report (xlsx, csv or a
  pasted table) and the source extracts (csv or xlsx). Output: a one-page tie-out note, a differences table and the
  printed checks. Does NOT fix the sources, restate the report, or decide which side is right. Do NOT use for a
  model-vs-model comparison with no system of record, for variance commentary (budget vs actual is a different
  question), or to audit a dashboard's SQL.
---

# Tie-out

One report, its sources, one page that says which figures tie and, for the ones that don't, how big the gap is and
where it most likely comes from. The person decides what to do about it. The skill never changes a number.

**Why it exists.** Employers now write this task into the job: "stand behind the tie-outs between the model, the
general ledger and the reported figures" and "flag a variance rather than quietly bridge it" (InStride, 2026-09),
"the CRM says $420,000, the processor shows $365,000, the dashboard reports $448,000, which is right" (Lepre,
2026-09). The hard part isn't the subtraction. It's doing it the same way every month, printing the checks, and
refusing to pick a winner the data can't pick. Source: Kinetric's job-description corpus, read October 2026
(internal pointer in `references/internal.md`).

## Two surfaces, one skill

| | Plain surface (the report owner) | Technical surface (the analyst) |
|---|---|---|
| Gives the skill | The report and the source files, dropped in a folder | The same, plus `matching_rules.json` they can edit |
| Reads | `tie_out_note.md`: one page, headline count, one sentence per difference, what it cannot tell you | The note plus `checks.txt` (rows in, rows out, period, duplicates, tolerance) and `differences.csv` |
| Can change | Nothing. Claude asks before any assumption is made | Tolerance, period, account mapping, sign, derived formulas |
| Stops at | Anything that needs the business's history to settle | Same; that stop is written into the note |

## Procedure

1. **Collect.** The report and every source extract go in one working folder per run, outside this skill's
   folder. Nothing is edited in place; the originals stay as received.
2. **Shape the report.** Produce `report.csv` with two columns, `figure,value`, one row per number on the page.
   Show the owner the table and ask them to confirm it is the page as they'd send it. A figure that appears twice
   on the page with two values is a finding already; say so.
3. **Write the matching rules.** `matching_rules.json` (schema in `references/matching_rules.md`). For the plain
   surface, Claude drafts it from account names and the source's own labels, then asks in plain words: "Revenue on
   your page is accounts 4000 and 4010 in the GL, September 1 to 30. Is that right?" One question per figure, in
   one message. Nothing is assumed about which source wins; the rules only say what to compare.
4. **Run.** `python scripts/tie_out.py --report report.csv --rules matching_rules.json --out .` from the working
   folder. Exit 0 means every figure had a rule and every source loaded. Exit 1 means the note was written but a
   figure had no rule or a source was empty; the note says which. Exit 2 means the inputs were unreadable and
   nothing was written. Never hand over a note from a run that exited 2.
5. **Deliver.** Hand the owner `tie_out_note.md`. Hand the analyst the folder. Do not summarise the note in chat
   beyond its headline line; the note is the deliverable.
6. **Log.** `run_log.csv` in the working folder gets one line per run (the script writes it).

## Hard rules

- **Never change a number.** Not in the report, not in the source, not in the note. A difference is reported, not
  bridged.
- **Never pick the winner.** The note says what each side contains and what would settle it. "Which date basis
  does your board expect" is the owner's question, and it is the funnel: finding and testing that rule is the
  paid work (kinetric.co/checks says what).
- **Every figure gets a verdict.** TIES, DIFFERS, NO RULE, or NO SOURCE ROWS. A figure with no rule is never
  silently dropped.
- **Tolerance is stated, once, in the rules, and printed in the note.** Default: $1.00 absolute or 0.1% of the
  source total, whichever is larger. The analyst can change it; the owner is told what it is.
- **Causes are detected by rule, not by guess.** Timing (rows outside the period that sum to the gap), duplicate
  (an id that appears more than once whose extra amount equals the gap), rounding scale (the gap is within half a
  unit per line), page arithmetic (the page's own total disagrees with the page's own components), carried (a
  derived figure inherits a component's gap). Anything else is *unexplained*, and the note says so.
- **The fixed last section stays.** *What this cannot tell you* is in every note, verbatim from the template, with
  one line per unexplained or judgement-bound difference.
- **Client data stays in the working folder** and is never copied into the skill, the repo's examples, or a chat.
  The example pack in `references/example/` is synthetic and labelled so.

## The ten fundamentals (Kinetric's rule for every automation; the list is in the repo README)

| # | Rule | How this skill meets it |
|---|---|---|
| 1 | One source of truth, named | Each source is named in the rules and printed in the note's header |
| 2 | Counts in, counts out | `checks.txt`: rows read, in period, outside period, blank, duplicate ids, per source |
| 3 | Reconciles to something | The whole skill; tolerance printed |
| 4 | Idempotent | Same inputs, same outputs; the log line is the only append |
| 5 | Fails loudly | Exit 2 on unreadable inputs, nothing written; exit 1 with the gap named in the note |
| 6 | Scheduled, with a log | `run_log.csv`, one dated line per run; scheduling is the owner's cron or a routine |
| 7 | Secrets out of the code | Reads local files only; no credentials |
| 8 | Versioned | The script records its own git commit in the log line when run inside a repo |
| 9 | Documented | This file and `references/matching_rules.md` |
| 10 | Human gate | The note is handed to a person; nothing is sent or changed |

## Test record

`references/example/` holds a synthetic September 2026 month-end pack with three planted differences (a timing
difference, a rounding difference, a duplicated journal). `references/example/TEST_RECORD.md` records the run and
confirms both surfaces find all three. Re-run `python scripts/make_example.py` then `tie_out.py` on it after any
change to the script; the outputs must match the record.
