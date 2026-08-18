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

### 8. A missing digest that was never missing — and the duplicate it caused
**Symptom** — no digest by 11:00 MYT on 13 Aug. Nothing in the Actions tab.
**Diagnosis at the time** — that renaming the default branch had deregistered
the cron. A manual run was triggered at 03:03 UTC to recover the day.
**What actually happened** — the scheduled run fired normally at 03:28 UTC, 25
minutes later. The user received **two contradictory emails**: "1 underpriced
flight — KL→Makassar 23% off" at 11:18 MYT, then "No KL→Indonesia deals today"
at 11:43. The second was correct behaviour — repeat-suppression had already
recorded the Makassar alert — but the pair reads as the service contradicting
itself.
**Real cause** — the run was *late, not missing*, and the conclusion was drawn
two hours too early. Every scheduled run in this project's history has fired
between 02:55 and 04:16 UTC against a 01:00 cron; 03:00 UTC is earlier than
five of the eight recorded firings. The evidence at the time ("no run yet")
was equally consistent with "delayed" and "deregistered", and the wrong one
was chosen with more confidence than the evidence supported.
**Fix** — the delay is documented in `CLAUDE.md` and `docs/RUNBOOK.md` with a
"do not declare it missing before 05:00 UTC" rule; the liveness watchdog moved
from 04:00 to 06:00 UTC, since at 04:00 it would have called the 6 Aug run
(fired 04:16) missing while it was still running.
**Guarded by** — `D1`/`D2` and the watchdog, for genuine outages. Nothing
prevents a human from triggering a duplicate run by hand — which is why the
timing rule is written down rather than encoded.

**The lesson is about diagnosis, not scheduling.** "No run yet" is absence of
evidence. Checking when runs *historically* fire would have cost one API call
and avoided the duplicate entirely.

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

### 11. A stale price level kept reading as a fresh discount
**Symptom** — the 13 Aug digest led with "KL→Makassar 23% off, save MYR 139".
The fare had been exactly 469 for four consecutive days.
**Cause** — the only rarity requirement was on the z-score path. A plain
`discount >= 20%` qualified on its own, so when a route steps down to a new
level and holds there, it keeps scoring the same discount until the median
finally catches up. Makassar ran 960 → 774 → 608 → 608 → 608 → 469 → 469 →
469 → 469, and the "usual 608" was a price that no longer existed. Its
percentile climbed 0% → 17% → 29% → 38% across those days, visibly recording
that the fare had become ordinary while the headline still said 23% off.
**The email said so itself** — "only 38% of tracked days were this cheap" —
and the word "only" was applied to anything under 50%, so a figure that
contradicted the headline was dressed up as though it supported it.
**Fix** — `deal_percentile_guard` (0.25): a discount must also be rare. And
"only" now requires ≤25%; above that the percentile is stated plainly, so it
tempers the claim instead of flattering it.
**Effect on real history** — both genuine new lows on 10 Aug survive, as does
11 Aug at the 17th percentile. The 40th-percentile LBJ and 29th-percentile UPG
alerts on 12 Aug drop, and 13 Aug goes from one stale alert to none.
**Guarded by** — four regression tests reconstructing the Makassar series, and
the replay harness, which now shows the difference on recorded data.

### 12. A partial scrape was published as if it were a full scan
**Symptom** — the 17 Aug digest reported KL→Ambon at MYR 1,787 (794 the day
before) and KL→Banjarmasin at 878 (429 the day before). Six routes were
inflated, +22% to +125%.
**Cause** — the provider returned prices for only a handful of the 30 scanned
departure dates on those routes: Ambon 1, Labuan Bajo 1, Kendari 1, Balikpapan
2, Banjarmasin 3, Sorong 4. The digest published the minimum of those samples
as the route's cheapest fare, in the same column and styling as routes with
full coverage, under a footnote asserting the figures were "cheapest across the
30 departure dates scanned". **Every distorted route moved upward** — the dates
that go missing are disproportionately the cheap ones, so a thin scan always
reads high.
**Why nothing caught it** — `D4` asks how many dates were *scanned* (a correct
30). Nothing asked how many came *back*. Coverage was invisible end to end: not
in the digest, not in the payload, not in the history.
**Fix** — `min_date_coverage` (0.25). Below that share a route cannot alert, is
labelled "partial scan · only N of 30 dates returned" in the table, and is not
written to history at all — recording an inflated daily-cheapest raises the
median and makes an ordinary fare tomorrow look like a deal.
**Guarded by** — `D7`, plus four tests reconstructing the Ambon case. Replaying
recorded history, `D7` fires on exactly those six routes on 17 Aug and on
KL→Bandung (6/30) on 14 Aug, and on nothing else.

### 13. The replay harness silently read no per-date history
**Symptom** — found while building `D7`: every route in every replayed day
reported 1 of 30 dates.
**Cause** — `date_prices.json` nests its contents under a `series` key. The
replay loaded the file raw, so it iterated `{"series", "schema_version"}`,
matched nothing, and got an empty mapping — indistinguishable from "no per-date
history recorded yet". The same wrong shape was being handed to `find_deals`,
so the same-date annotation never fired in a replay either.
**Fix** — the replay uses `load_date_series()`, the service's own loader, and
prints how many series it loaded so an empty read is visible rather than
assumed.
**The general lesson** — a loader that returns empty on malformed input is
convenient in production and dangerous in a test harness, where "no data" and
"data I failed to read" produce identical, passing output.

### 14. Coverage slid by a third and every run reported success
**Symptom** — "fares checked" fell 3,191 → 2,487 → 1,793 across 16-18 Aug. On
18 Aug the flagship route, KL→Jakarta, was priced from **2 of 30** departure
dates; Medan from 2, Padang from 3, Pekanbaru from 6, Surabaya from 7.
**Cause** — the provider answers a throttled request with **HTTP 200 and an
empty itinerary list**, which is byte-for-byte identical to "no flights on this
date". Shard 0's log for 18 Aug reads `collected 377 offers, 0 error(s)` while
90 of its 210 searches returned nothing at all. Every shard degraded together
(77-91% → 57-78%), so it is not one throttled runner.
**What this cost** — nothing crashed, no error was logged, no check fired, and
the digest read normally while a third of the window was missing.
**Fix** —
* `min_date_coverage` raised 0.25 → 0.50. Denpasar and Lombok at 8 of 30 had
  cleared the old bar and were published unlabelled next to fully scanned
  routes. The cheapest of less than half a window is not that window's minimum.
* The digest header now states coverage outright — *"67% of scanned departure
  dates returned a price"* — in red below 75%. A slow slide is the dangerous
  shape, and the person reading the email is the one guaranteed to be looking.
* An empty search is re-asked once after a longer pause, budgeted at 60 per
  shard so a badly throttled run cannot triple its own request volume. **Whether
  this helps is unknown**; the run logs how many retries recovered a price, so
  the next few days answer the question with evidence instead of assumption.
**Guarded by** — `D8` (run-level coverage against a 75% floor) alongside `D7`
(per-route). Replaying recorded history, `D8` fires on 17 and 18 Aug and on no
other day.

### 15. A log line that reported the opposite of what happened
**Symptom** — found immediately, in the test output of the fix above: `retried
60 empty search(es)` printed on runs using the offline mock provider, which
never retries anything.
**Cause** — the count was inferred as `budget - remaining`. Offline providers
start at a budget of zero, so the subtraction reported the full configured
budget as "used".
**Fix** — count what was actually re-asked.
**Why it is worth an entry** — a log line stating the opposite of what happened
is worse than no log line. The next person diagnosing a coverage problem would
have read "retried 60, recovered 0", concluded the retry was useless, and
removed it — on evidence that was pure arithmetic error.

---

## Known risks, not yet guarded

### Intra-day scrape variance is larger than expected
On 13 Aug two runs happened 25 minutes apart, giving an unplanned controlled
experiment. Two routes disagreed:

| Route | 11:18 run | 11:43 run | Spread |
|---|---|---|---|
| KL→Manado | MYR 820 (6 Sep) | MYR 1,107 (1 Sep) | **1.35×** |
| KL→Denpasar | MYR 428 (12 Sep) | MYR 459 (6 Sep) | 1.07× |

Fares do not move 35% in 25 minutes. The later scrape simply failed to see the
6 Sep itinerary. History self-heals — `daily_cheapest` keeps the minimum across
runs, so 820 was stored — but **the email reports the run's own scrape**, so
the second digest showed 1,107 for a route the system already knew cost 820.

No check catches this: a single run has nothing to compare against. The honest
mitigation would be scanning each route twice and taking the minimum, at double
the request budget. Recorded rather than fixed.

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
