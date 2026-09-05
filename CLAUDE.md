# Working on Cheap Flights Tracker

A daily job scrapes KL→Indonesia fares, decides which are unusually cheap, and
emails a digest. It runs unattended on GitHub Actions and nobody reads the logs.

Read this before changing anything in `flightdeals/` or `.github/workflows/`.

---

## The one thing to understand about this project

**Every defect that has shipped here produced a plausible-looking email.** Not
a crash, not a stack trace, not a red X — a digest that arrived on time and
read perfectly sensibly while being wrong. Several ran for days before a human
noticed something odd about the numbers.

The tests were green for all of them.

So the standing rule is: *"the tests pass" is not evidence that a change is
correct.* It is evidence that it did not crash. Correctness here means the
numbers in the email are true, and only the replay harness and the auditor can
tell you that.

```bash
python -m unittest discover -s tests   # necessary, nowhere near sufficient
python scripts/replay_audit.py --all   # what actually catches things
```

`replay_audit.py` re-runs past days against real recorded history and puts each
resulting digest through the independent auditor. **Run it before every commit
that touches the detector, the statistics, the baselines or the emailer.** If it
reports a BLOCK, the change is wrong on data that really occurred.

---

## Invariants — breaking any of these has caused an incident

1. **A baseline is built from daily-cheapest fares, never from every offer.**
   Most offers on a given day are worse than that day's best, so pooling them
   drags the baseline upward and makes ordinary fares look underpriced.
2. **One-way and round-trip fares never share a baseline.** A return costs
   roughly double; a pooled median sits between the two and makes every one-way
   look about half price.
3. **A baseline only ever uses observations from strictly before the run date.**
   A fare must not help set the standard it is judged against.
4. **Only a route's own cheapest fare is ever an alert candidate.** Scoring all
   30 departure dates and keeping the best discount turns per-date noise into a
   search: with 30 chances nearly every route finds one date whose previous
   reading was junk.
5. **No alert without an absolute floor.** A z-score alone is meaningless — a
   route sitting at one fare all week has a tiny scale, so a trivial dip scores
   z = −4.75. Every qualifying path also requires ≥12% off and ≥MYR 40 saved.
6. **The 30-day window is scanned exhaustively, never sampled.** Google prices
   each date separately, so a date not probed is a price that cannot be seen.
   The far-horizon lane (`flightdeals/horizon.py`) is exhaustive too, within
   each of its two 30-day blocks — it was sampled once, and could not support
   its own conclusion: 10 of 30 dates misses the true cheapest fare 41% of the
   time and reads a mean 13.9% high, the same size as the discount it existed
   to detect. **Coverage is the bias**: a window at 50% coverage reports a
   minimum ~12% too high, at 80% ~3.6%, so the two windows are only compared
   when both clear 80%. Do not merge their stores either: a 150-day fare and a
   20-day fare are different populations, and pooling them repeats invariant
   2's failure in a new place. **The far blocks are anchored to the day the
   store was scanned, not to the day it is read.** That lane is scanned weekly
   and read daily; recomputing the window from the digest date slid it off the
   scanned dates a day at a time until coverage fell through the 80% floor and
   the section silently stopped appearing five days into every week.
7. **`MIN_SAMPLES` is a safety floor, not a tuning knob.** It was once lowered
   to 1 "to get more alerts". 21 of 26 routes alerted the next morning off
   single junk readings.

## Data files are bot-owned

`data/price_history.json`, `data/date_prices.json` and `data/alert_state.json`
are written by the daily run and committed back by the bot. Do not hand-edit
them — you are editing the evidence the auditor uses to check the code. If a
fixture is needed, build it in the test.

## Scheduled workflows run late — always

The cron says 01:00 UTC. **No scheduled run in this project's history has ever
started on time.** Every one has fired between 02:55 and 04:16 UTC — a delay of
115 to 196 minutes. GitHub queues `schedule:` triggers best-effort and drops
them under load; that is documented behaviour, not a fault here.

**Do not declare a run missing before about 05:00 UTC (13:00 MYT).** On 13 Aug
the digest was declared missing at 03:00 UTC, a manual run was triggered at
03:03, and the real scheduled run arrived at 03:28 — so the user got two
contradictory emails 25 minutes apart, one announcing a deal and one announcing
none. The outage was imaginary; the duplicate was not.

A separate, real hazard: GitHub registers `schedule:` triggers against the
**default branch** and refreshes them on push, so renaming the default branch
can stop the cron until the next commit lands. That is worth knowing, but it
was *not* what happened on 13 Aug. Check the timestamps of recent `schedule`
runs before reaching for it — if they show the usual 2-3 hour delay, the
schedule is fine and you are simply early.

## Verifying your own edits actually applied

Two attempts to add map links were made with scripted string replacements that
matched nothing, silently succeeded, and shipped a feature that was not there.
The tests still passed, because they asserted on functions that had been
rewritten out from under the patch.

- Prefer real file edits over scripted find-and-replace.
- When a replacement is scripted, `assert` the match count before writing.
- Verify a rendering change by **counting occurrences in the rendered output**,
  not by checking that some test passed:

  ```bash
  python run.py --provider mock --dry-run >/dev/null
  grep -o "maps/search" artifacts/digest.html | wc -l
  ```

  Use `grep -o | wc -l`, not `grep -c` — the latter counts matching *lines*,
  and the template puts several links on one line.

## Secrets

SMTP credentials live in GitHub Secrets only. `.env` is gitignored and stays
that way. Nothing goes in a file, a log line, or a commit message.

---

## Where things are

| Path | What it does |
|------|--------------|
| `flightdeals/` | the service: config, search, baseline, detector, emailer |
| `qa/` | the independent auditor — must not import `flightdeals` |
| `scripts/replay_audit.py` | replay recorded days past the auditor |
| `scripts/check_liveness.py` | did the job run at all? |
| `scripts/price_lookup.py` | what have we ever seen for a route? (`--all` for every route) |
| `docs/POSTMORTEMS.md` | every incident, with the check that now catches it |
| `docs/RUNBOOK.md` | what to do when the digest looks wrong or stops |
| `docs/COMPETITOR-ANALYSIS.md` | industry techniques surveyed, with a verdict on each |

The `qa/` package deliberately re-implements the statistics rather than
importing them. That duplication is the entire point: two independent
derivations that agree is evidence, one implementation checking itself is not.
**Do not "clean this up" by having `qa/` import from `flightdeals/`.**
