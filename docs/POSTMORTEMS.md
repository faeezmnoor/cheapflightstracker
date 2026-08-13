# Incidents, and what now catches them

Every defect this project has shipped, the check that guards it today, and the
ones still unguarded.

The point of writing them down is not record-keeping. It is that **each entry
is the specification for a check** — and a check whose motivating failure has
been forgotten is the first thing to get relaxed when it becomes inconvenient.

---

## The pattern

Read the list and one thing stands out: **not one of these crashed.**

Every single incident produced a digest that arrived on time, rendered
correctly, and read plausibly. Exit code 0. Tests green. Several ran for days
before a human noticed the numbers were odd.

That is why the QA layer checks *output against independently derived truth*
rather than checking that the code runs. Running was never the problem.

---

## Shipped defects

### 1. One-way and round-trip fares shared a baseline
**Symptom** — nearly every one-way fare showed as ~50% underpriced.
**Cause** — a return ticket costs roughly double, so a pooled median sat
between the two populations, making every one-way look like half price.
**Fix** — baselines keyed on `(route, trip_type)`.
**Guarded by** — `C5`, which recomputes the baseline per trip type from raw
history and disagrees loudly with a pooled one.

### 2. Baseline built from every offer, not each day's cheapest
**Symptom** — a systematic bias towards "deal"; ordinary fares looked cheap.
**Cause** — most offers on any given day are worse than that day's best, so
averaging them all dragged the baseline upward.
**Fix** — reduce each day to its cheapest fare before computing anything.
**Guarded by** — `C5`. The independent derivation reduces to daily-cheapest, so
a baseline built any other way fails to reproduce.

### 3. Only two departure dates were probed
**Symptom** — the user found MYR 339 on Google Flights that the digest had
never seen.
**Cause** — date sampling. Google prices each date separately, so a date not
probed is a price that cannot exist as far as the service is concerned.
**Fix** — exhaustive scanning of the full 30-day window; the request budget was
handled by sharding, not by sampling.
**Guarded by** — `D4`.

### 4. Point-of-sale parameters missing
**Symptom** — prices that did not match what a Malaysian shopper sees.
**Cause** — no `gl`/`hl`/`curr` on the request, so Google priced for the
US datacenter the runner happened to sit in.
**Fix** — `LocalizedFetcher`.
**Guarded by** — `C6` catches mixing. Silent single-market drift is **still
unguarded** — see below.

### 5. Yogyakarta configured as JOG
**Symptom** — the route returned nothing, every day, forever.
**Cause** — JOG handles domestic traffic only. It never errored; it was simply
always empty, and an empty route looks exactly like a route with no cheap
fares.
**Fix** — switched to YIA; `scripts/probe_destinations.py` now validates
candidates before they are added.
**Guarded by** — `D3`, which distinguishes "never returned a fare" (usually a
wrong airport code) from "worked, then went silent".

### 6. `MIN_DATE_SAMPLES` lowered to 1
**Symptom** — the worst incident. 21 of 26 routes alerted in one morning. One
claimed "KL→Batam 85% off" against a single junk reading of 2,110. Another
quoted 309 while the table on the same email showed 279.
**Cause** — three faults compounding: a baseline of one observation; selecting
the best discount across 30 dates, which turned per-date noise into a search;
and choosing the candidate by discount rather than by price.
**Fix** — the full statistical rework — robust statistics, one candidate per
route (its cheapest fare), absolute floors on every qualifying path.
**Guarded by** — `C1` (alert vs table), `C2` (alert rate), `C3` (baseline
thickness), `C5` (independent recomputation). Four checks, because it was four
bugs wearing one coat.

### 7. Map links silently never rendered — twice
**Symptom** — the feature was absent from the email. Tests passed.
**Cause** — scripted string replacements targeting code that had already been
rewritten. They matched nothing, reported success, and changed nothing.
**Fix** — real edits, and the count of `maps/search` occurrences in the
rendered HTML checked directly.
**Guarded by** — `C7`, plus the standing rule in `CLAUDE.md`: verify a
rendering change by counting the rendered output, never by a passing test.

### 8. Renaming the default branch deregistered the cron
**Symptom** — no digest on 13 Aug. No failed run, no notification, nothing in
the Actions tab at all.
**Cause** — GitHub registers `schedule:` triggers against the default branch
and refreshes them on push. The rename dropped the registration.
**Fix** — a commit re-registered it; the failure mode is documented in the
workflow header.
**Guarded by** — `D1`/`D2` (history stops advancing) and the liveness watchdog.
**Partially.** See below — this one is not fully solved.

### 9. `--dry-run` wrote to the real price history
**Symptom** — found while building the QA layer, not in production. Running
`python run.py --provider mock --dry-run` twice added 52 invented fares to
`data/price_history.json` alongside the day's 26 real ones.
**Cause** — `dry_run` suppressed the *email* but not the persistence. The daily
workflow happened to be safe because a separate `if:` guards the commit step,
so the corruption only ever landed on a developer's checkout — where it would
have silently poisoned every baseline used to judge future alerts.
**Fix** — `report()` returns before persisting anything when `dry_run` is set.
**Guarded by** — a test that runs the report path against temp files and
asserts all three are byte-identical afterwards.

**Worth noting how this was found:** not by reading the code, but by running
the documented verification command twice and noticing a number change between
runs. The render count dropped from 48 to 26 because the first run had polluted
the history the second run compared against. Checking output rather than
intent is the whole method.

### 10. README advertised Python 3.9 support that never existed
**Symptom** — caught by the new CI matrix on its first run: `pip install -r
requirements.txt` failed outright on 3.9.
**Cause** — `fast-flights` has required `>=3.10` all along. The badge was
written from assumption and never tested, because until now nothing in CI
installed the dependencies on any version but 3.11.
**Fix** — badge corrected to 3.10+, matrix floor moved to 3.10.
**Guarded by** — the CI matrix itself. A version claim that is not built is
not a claim, it is a guess.

---

## Known risks, not yet guarded

Honest list. These are the things that would hurt next.

### The watchdog shares fate with what it watches
`liveness.yml` is itself a scheduled workflow on the same default branch. It
catches "ran and produced nothing", "run failed", and "data went stale". It
**cannot** catch "GitHub stopped scheduling anything", which is precisely
incident 8.

Closing it needs a heartbeat from outside GitHub — a free uptime pinger against
a URL the run updates, or a calendar reminder to glance at the Actions tab
weekly. Until then the residual risk is real: a repeat of incident 8 costs a
day, and the first signal is a human noticing the silence.

### Point-of-sale drift
`C6` catches currencies *mixing*. It cannot tell that every price is wrong in
the same direction because the runner was served a different market. Detecting
that needs an external reference price, which the service does not have.

### Threshold calibration as history deepens
The thresholds were set against about a week of data. As baselines thicken,
their distribution changes character — MAD tightens, and the same absolute dip
scores a larger z. `C2`'s alert-rate ceiling is the backstop, but the right
move is to revisit the thresholds once ~30 days have accumulated rather than
wait for the ceiling to trip.

### Alert state is not backed up
If `data/alert_state.json` is lost, every currently-cheap route re-alerts once.
Noisy, self-healing, low priority — noted so it is not diagnosed twice.

### The provider is unofficial and can change without notice
`fast-flights` reads a Google endpoint that has no stability contract. `D6`
now catches a wholesale outage on the day it happens; a *partial* format change
that silently drops the cheap itineraries on some routes would still look like
a quiet market.

---

## Adding a check

Two rules, both learned the hard way:

1. **A check needs a test that reconstructs the failure it catches.** Otherwise
   it is untested code in the highest-trust position in the system.
2. **The clean-digest test must still pass.** A checker that fires on good
   digests gets switched off within a week, and then guards nothing at all.
