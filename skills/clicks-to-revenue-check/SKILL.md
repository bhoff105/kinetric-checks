---
name: clicks-to-revenue-check
description: >-
  Tie an ad platform's reported revenue by campaign to the store's own orders before the number goes in a client
  report: each campaign's platform claim is matched to the Shopify orders carrying its UTMs for the period, every
  gap is sized and given its most likely cause (attribution-window timing, a double-exported order, rounding), and
  nothing is bridged. Use when Brendan, an agency or a brand says "/clicks-to-revenue-check", "Meta says X but
  Shopify says Y", "check the ROAS before the client sees it", "do the platform numbers match the store", or hands
  over a platform revenue export plus a Shopify order export. The marketing twin of /tie-out, run on the same
  engine. Output: a one-page note, a differences table, the printed checks. Does NOT set the attribution window,
  pick which platform's claim is right, touch tags, pixels, GTM or CAPI, or change any number. Do NOT use for
  tag-side diagnosis (outside Kinetric's expertise, ruled 2026-10-09) or for incrementality questions.
---

# Clicks-to-revenue check

The ad platform says a campaign made $X. The store's orders carrying that campaign's UTMs add up to $Y. This skill
puts the two side by side for every campaign, says how far apart they are, and tests each gap for the three
causes that explain most of them. It runs `/tie-out`'s engine with the platform's claim as the page and the
store's orders as the source. Nothing is changed; the person decides.

**Why it exists.** Agencies report to brands monthly and "in that report the platform ROAS and the store's own
orders disagree, and someone closes the gap by hand" (Kinetric's own agency outreach). Grain Group's posting
(2026-10) asks the analyst to "fix breaks before they reach client reporting". Smyle's asks them to "investigate
why reports or systems do not match". This is that step, done the same way every month, with the checks printed.
It is the free, read-side version of Kinetric's Clicks to Revenue work. Source for the demand: Kinetric's
job-description corpus, October 2026 (internal pointer in `references/internal.md`).

## Two surfaces, one skill

| | Plain surface (the account lead, the brand owner) | Technical surface (the analyst) |
|---|---|---|
| Gives the skill | The platform's revenue-by-campaign export and the store's order export | The same, plus `matching_rules.json` they can edit |
| Reads | `tie_out_note.md`: "3 of 6 campaigns tie", one sentence per gap | The note plus `checks.txt` and `differences.csv` |
| Can change | Nothing. Claude asks before mapping a campaign to its UTMs | Period, window, UTM mapping, tolerance |
| Stops at | Which attribution window the brand should use. That is a rule set by habit, and Kinetric's paid work | Same |

## Procedure

1. **Collect.** The platform export (campaign, reported revenue, for one period) and the store's order export with
   `order_id`, `order_date`, `utm_source`, `utm_campaign`, `total`. One working folder; originals untouched.
2. **Shape the page.** `report.csv` with `figure,value`: one row per campaign exactly as the platform names it,
   plus the platform's total if it prints one. Show it to the owner and confirm it is the number they report.
3. **Write the rules.** `matching_rules.json` as in `../tie-out/references/matching_rules.md`: one figure per
   campaign with a `filter` on `utm_source` and `utm_campaign`, the period, a timing window equal to the
   platform's click window (7 days for Meta's default, 30 for Google's), tolerance $1.00 or 0.01%. The total is a
   `derived` sum of the campaign figures. Ask the owner, in plain words, one question per campaign: "Meta's
   'Prospecting' is orders whose UTMs are source meta, campaign prospecting. Right?"
4. **Run.** `python ../tie-out/scripts/tie_out.py --report report.csv --rules matching_rules.json --out .`
   Exit codes as in `/tie-out`. Never hand over a note from an exit 2.
5. **Deliver.** The note to the owner, the folder to the analyst. The headline is the only line repeated in chat.
6. **Log.** `run_log.csv` is written by the engine.

## Hard rules

- **Never change a number**, on either side. A gap is reported with its size and its likely cause.
- **Never pick the winner.** Platform and store count different things on purpose (click windows, view-through,
  refunds, currency). Which one the brand should report is the owner's rule to find, and that is the paid work.
- **Never go tag-side.** If the gap is unexplained, the note says so. It does not suggest pixel, GTM, CAPI or
  Consent Mode work; that is a stated limit of Kinetric's practice.
- **Every campaign gets a verdict.** TIES, DIFFERS, NO RULE, NO SOURCE ROWS. A campaign on the platform with no
  orders in the store is a finding, not a blank.
- **Causes are detected by rule** (the engine's detectors), and *unexplained* is an allowed answer.
- **Client data stays in the working folder.** The example in `references/example/` is synthetic and says so.

## The ten fundamentals (Kinetric's rule for every automation; the list is in the repo README)

Identical to `/tie-out`'s table; the engine is shared. The one addition: the period and the click window are
printed in the note's header, since the window is the assumption most likely to be wrong.

## Test record

`references/example/` is a synthetic September 2026 store with four campaigns on two platforms and three planted
gaps (attribution-window timing, a double-exported order, platform rounding). `TEST_RECORD.md` records the run.
Re-run `python scripts/make_example.py` and the engine after any change to `tie_out.py`.
