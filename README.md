# Kinetric Checks (archived)

> **This repo is archived and no longer updated.** Kinetric's free skills now live at
> [bhoff105/kinetric-essentials](https://github.com/bhoff105/kinetric-essentials): reporting standards, variance
> analysis, root cause analysis and an executive summary, each tested on known answers. The checks below are kept
> as they were, read only.

Free Claude Code skills that check the numbers before they go out. Each one ties a figure someone is about to
send to the source it came from, lists every difference with its size and its most likely cause, and refuses to
bridge anything. They augment the person who owns the numbers rather than replace them: the check does the
tying-out the same way every month, and the call stays with that person. Built by
[Kinetric](https://kinetric.co). MIT licensed.

Every check has two surfaces. Drop the files in and read the one-page note, or open `checks.txt` and the rules
file and change the tolerance, the period, the mapping. Both surfaces are tested on a synthetic pack with planted
differences before a check ships; the record is in each skill's `references/example/TEST_RECORD.md`.

## Month-end checks

| Skill | What it does | Status |
|---|---|---|
| `tie-out` | Every figure on a report page tied to its source rows. Gaps tested for timing, a duplicated id, rounding scale, page arithmetic. | Built, tested |
| `variance-commentary` | Budget vs actual in, first-draft commentary out, every number traced to a row. | Next |
| `bridge-page` | A revenue or P&L bridge from one period to the next, each step tied to its rows. | Next |

## Campaign checks

| Skill | What it does | Status |
|---|---|---|
| `clicks-to-revenue-check` | An ad platform's revenue by campaign tied to the store's orders carrying its UTMs. Gaps tested for attribution-window timing, a double-exported order, platform rounding. | Built, tested |
| `test-readout` | An A/B or holdout result read against the rule written down before the test ran. | Planned |
| `report-refresh` | The weekly report rebuilt from source with its counts printed and compared to last week's. | Planned |

## How to use one

1. Copy the skill folder into your project's `.claude/skills/`.
2. Open Claude Code and say `/tie-out` (or the skill's name) with your report and your source extracts.
3. Read `tie_out_note.md`. If you are the analyst, read `checks.txt` and edit `matching_rules.json`.

Each skill's `SKILL.md` has the full procedure. The scripts use only the Python standard library.

## What they cannot tell you

Which side is right. A check shows where two numbers disagree and how big the gap is. It does not know which
date basis your board expects, which attribution window your brand should report, or whether a duplicated journal
was meant to be reversed. Those are rules someone set once, usually by habit. Finding each one, writing it down and
testing it against your own history is what Kinetric does for a fee, and sometimes the honest answer is that the
rule you have is fine.

## Ten things every check must do

Each skill carries a table showing how it meets these: one named source of truth; counts in and counts out;
reconciles to something with a stated tolerance; idempotent; fails loudly; scheduled with a log; secrets out of the
code; versioned; documented for the next person; a human gate where money or a stranger is involved.
