<!-- layer: knowledge · status: living (append at top) · verified: 2026-10-06 -->
# Lessons — cheapflightstracker

Every AGENTS.md §6 rule links here or to a decision. A lesson without a home is not yet applied.

The pattern across all of them: not one of these crashed. Each produced a digest that arrived on time, rendered correctly and read plausibly, with exit code 0 and green tests. The full narrative of L-01 to L-16 is in docs/records/postmortems.md (same numbering as its "Shipped defects" entries). Dates are the date each was found, where the record states one; "2026-08" means found in August 2026 without a recorded day.

| Id | Date | What happened | Cost | The rule | Where the rule lives |
| --- | --- | --- | --- | --- | --- |
| L-01 | 2026-08 | One-way and round-trip fares shared a baseline, so a pooled median sat between the two populations. | Nearly every one-way fare showed about 50% underpriced. | One-way and round-trip fares never share a baseline; baselines are keyed on (route, trip_type). | AGENTS.md §6 rule 2; check `C5` in qa/ |
| L-02 | 2026-08 | The baseline was built from every offer, not each day's cheapest, dragging it upward. | Systematic bias towards "deal"; ordinary fares looked cheap. | A baseline is built from daily-cheapest fares, never from every offer. | AGENTS.md §6 rule 1; check `C5` in qa/ |
| L-03 | 2026-08 | Only two departure dates were probed, so a date not probed was a price that could not exist. | The user found MYR 339 on Google Flights that the digest never saw. | Scan the 30-day window exhaustively; handle request budget by sharding, not sampling. | AGENTS.md §6 rule 6; check `D4` in qa/ |
| L-04 | 2026-08 | No `gl`/`hl`/`curr` on the request, so Google priced for the US datacenter the runner sat in. | Prices did not match what a Malaysian shopper sees. | Requests carry point-of-sale parameters (`LocalizedFetcher`). Silent single-market drift is still unguarded. | check `C6` in qa/ (mixing only) |
| L-05 | 2026-08 | Yogyakarta was configured as JOG, which handles domestic traffic only; the route returned nothing, every day. | A route silently empty forever; an empty route looks like a route with no cheap fares. | Validate candidate destinations before adding them (`scripts/probe_destinations.py`). | check `D3` in qa/; scripts/probe_destinations.py |
| L-06 | 2026-08 | `MIN_DATE_SAMPLES` was lowered to 1: a baseline of one observation, the best discount chosen across 30 dates, and the candidate chosen by discount rather than price. | The worst incident: 21 of 26 routes alerted in one morning, one claiming "KL→Batam 85% off" against a single junk reading. | One candidate per route (its cheapest fare), absolute floors on every qualifying path, `MIN_SAMPLES` is a safety floor not a tuning knob. | AGENTS.md §6 rules 4, 5, 7; checks `C1`, `C2`, `C3`, `C5` in qa/ |
| L-07 | 2026-08 | Map links never rendered, twice: scripted string replacements matched nothing, reported success and changed nothing. | A feature absent from the email while tests passed. | Verify your own edits applied: real file edits, assert the match count, count occurrences in the rendered output. | AGENTS.md §6 rule 10; check `C7` in qa/ |
| L-08 | 2026-08-13 | The digest was declared missing at 03:00 UTC, a manual run was triggered, and the scheduled run arrived 25 minutes later. | Two contradictory emails 25 minutes apart. | Scheduled runs fire 115 to 196 minutes late; do not declare a run missing before 05:00 UTC. Diagnose from evidence (when runs historically fire), not absence of evidence. | AGENTS.md §6 rules 8, 9; docs/runbooks/digest.md; liveness watchdog; checks `D1`, `D2` in qa/ |
| L-09 | 2026-08 | `--dry-run` suppressed the email but not persistence, writing 52 invented fares into `data/price_history.json`. | Corrupted only a developer checkout (the workflow's commit step is guarded), but would have poisoned every future baseline. | A dry run must persist nothing; `report()` returns before persisting when `dry_run` is set. | test asserting the three data files are byte-identical after a dry run |
| L-10 | 2026-08 | The README advertised Python 3.9 support that never existed (`fast-flights` requires 3.10 or later). | Caught by the new CI matrix on its first run. | A version claim that is not built is not a claim, it is a guess. | CI matrix in .github/workflows/ci.yml |
| L-11 | 2026-08-13 | A stale price level kept reading as a fresh discount: Makassar held at 469 for four days and the digest led with "23% off". | The headline contradicted the email's own percentile figure. | A discount must also be rare (`deal_percentile_guard` 0.25); "only" requires 25% or less. | detector (`deal_percentile_guard`); four regression tests; replay harness |
| L-12 | 2026-08-17 | A partial scrape (1 to 4 of 30 dates returned) was published as if it were a full scan, every distorted route moving upward. | Six routes inflated +22% to +125% in the digest. | A route below `min_date_coverage` cannot alert, is labelled a partial scan, and is not written to history. | check `D7` in qa/; four tests |
| L-13 | 2026-08 | The replay harness read no per-date history: `date_prices.json` nests under `series` and the replay loaded it raw. | Every replayed route reported 1 of 30 dates; "no data" and "data I failed to read" looked identical. | Use the service's own loader (`load_date_series()`) and print how many series loaded; a loader that returns empty on malformed input is dangerous in a test harness. | scripts/replay_audit.py |
| L-14 | 2026-08-16 | The provider answers a throttled request with HTTP 200 and an empty list, identical to "no flights"; coverage slid by a third with 0 errors logged. | "Fares checked" fell 3,191 to 1,793; flagship KL→Jakarta priced from 2 of 30 dates. | `min_date_coverage` is 0.50, the digest header states coverage (red below 75%), empty searches are retried once within a budget of 60 per shard. | checks `D7`, `D8` in qa/ |
| L-15 | 2026-08 | A log line reported the opposite of what happened: `retried 60 empty search(es)` on a provider that never retries. | A diagnosing human would have concluded the retry was useless and removed it. | Count what was actually done, never infer it by subtraction; a log line stating the opposite of what happened is worse than none. | the retry counter in the search path |
| L-16 | 2026-08 | CI answered two questions with one red X: `replay_audit.py --strict` failed on data-health `WARN` findings that no pusher could fix. | Every push red from 17 Aug; a permanently red build is a build nobody reads. | `BLOCK` always fails; a code `WARN` (`C*`) fails under `--strict`; a data `WARN` (`D*`) never gates a push. Every check needs a test reconstructing its failure, and the clean-digest test must still pass. | AGENTS.md §6 rule 13; tests on check classification; liveness watchdog |
| L-17 | carried over | A fare must not help set the standard it is judged against (no incident recorded in the postmortems). | Not recorded. | A baseline only ever uses observations from strictly before the run date. | AGENTS.md §6 rule 3 |
| L-18 | carried over | The far-horizon lane was sampled once and could not support its own conclusion. | 10 of 30 dates missed the true cheapest fare 41% of the time and read a mean 13.9% high, the same size as the discount it existed to detect. | The far-horizon lane is exhaustive within each of its two 30-day blocks; coverage is the bias; never merge the stores. | AGENTS.md §6 rule 6 |
| L-19 | carried over | `qa/` deliberately re-implements the statistics rather than importing them. | Not recorded. | Do not "clean this up" by having `qa/` import from `flightdeals/`. | AGENTS.md §4 and §6 rule 12 |

## Verbatim explanations carried over from the former CLAUDE.md

These are the explanations the one-line rules in AGENTS.md §6 stand on. Nothing was dropped in the migration.

### The standing rule (L-01 to L-16, AGENTS.md §1 and §6 rule 11)

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

### Invariants — breaking any of these has caused an incident

1. **A baseline is built from daily-cheapest fares, never from every offer.**
   Most offers on a given day are worse than that day's best, so pooling them
   drags the baseline upward and makes ordinary fares look underpriced. (L-02)
2. **One-way and round-trip fares never share a baseline.** A return costs
   roughly double; a pooled median sits between the two and makes every one-way
   look about half price. (L-01)
3. **A baseline only ever uses observations from strictly before the run date.**
   A fare must not help set the standard it is judged against. (L-17)
4. **Only a route's own cheapest fare is ever an alert candidate.** Scoring all
   30 departure dates and keeping the best discount turns per-date noise into a
   search: with 30 chances nearly every route finds one date whose previous
   reading was junk. (L-06)
5. **No alert without an absolute floor.** A z-score alone is meaningless — a
   route sitting at one fare all week has a tiny scale, so a trivial dip scores
   z = −4.75. Every qualifying path also requires ≥12% off and ≥MYR 40 saved. (L-06)
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
   2's failure in a new place. (L-03, L-18)
7. **`MIN_SAMPLES` is a safety floor, not a tuning knob.** It was once lowered
   to 1 "to get more alerts". 21 of 26 routes alerted the next morning off
   single junk readings. (L-06)

### Data files are bot-owned (AGENTS.md §4)

`data/price_history.json`, `data/date_prices.json` and `data/alert_state.json`
are written by the daily run and committed back by the bot. Do not hand-edit
them — you are editing the evidence the auditor uses to check the code. If a
fixture is needed, build it in the test.

### Scheduled workflows run late — always (L-08, AGENTS.md §6 rules 8, 9)

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

### Verifying your own edits actually applied (L-07, AGENTS.md §6 rule 10)

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

### Secrets (AGENTS.md §4)

SMTP credentials live in GitHub Secrets only. `.env` is gitignored and stays
that way. Nothing goes in a file, a log line, or a commit message.

### The `qa/` duplication is the point (L-19, AGENTS.md §6 rule 12)

The `qa/` package deliberately re-implements the statistics rather than
importing them. That duplication is the entire point: two independent
derivations that agree is evidence, one implementation checking itself is not.
**Do not "clean this up" by having `qa/` import from `flightdeals/`.**

### Adding a check (L-16, AGENTS.md §6 rule 13; from the postmortems' closing section)

1. **A check needs a test that reconstructs the failure it catches.** Otherwise
   it is untested code in the highest-trust position in the system.
2. **The clean-digest test must still pass.** A checker that fires on good
   digests gets switched off within a week, and then guards nothing at all.
