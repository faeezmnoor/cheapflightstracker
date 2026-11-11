<!-- layer: knowledge · status: living · verified: 2026-11-11 -->
# Digest auditor: the three questions

Moved verbatim from .claude/agents/digest-auditor.md (harness audit 2026-11); the agent reads it when it applies.

## Question 1 — is this alert real?

Recompute it independently. `qa/recompute.py` has the derivation; use it
directly rather than trusting `flightdeals/stats.py`:

```python
from qa.recompute import baseline_for
baseline_for(observations, "KUL-CGK", "one_way", before_date="2026-08-13")
```

Then check, in this order — these are the ways it has been wrong before:

- **How many days is the baseline built on?** Fewer than `MIN_SAMPLES` is not a
  baseline. A single prior reading once produced an "85% off" alert.
- **Is the trip type consistent?** A one-way judged against round-trip history
  looks about half price, and always will.
- **Is the alerted price the same as the route's cheapest in the table?** They
  once differed — the alert said 309 while the table said 279.
- **Is the "usual" price plausible?** A wild median usually means one junk
  scrape, not a real market. Check the day-by-day series before believing it.

## Question 2 — disagreement with Google Flights

Usually one of, in rough order of likelihood:

- **The date is outside the scanned window.** Only the next 30 days are probed.
- **Point of sale.** Google prices by market; the runner sets `gl`/`hl`/`curr`
  for Malaysia. A price seen in another market will differ legitimately.
- **The scrape missed the cheap itineraries.** Roughly 7% of dates swing more
  than 2× day to day from this alone. One reading is not a fact — check whether
  neighbouring days agree.
- **Time.** Fares move. The digest is a morning snapshot.

Say which one it is, with the evidence. Do not offer the list as a hedge.

## Question 3 — no email arrived

Check in this order, and stop at the first that explains it:

1. **Did the workflow run at all?** A missing `schedule` run in the Actions tab
   means the cron never fired — renaming the default branch deregisters it, and
   this has happened. There is no failed run to find, because there was no run.
2. **Did the run fail?** Check the job logs.
3. **Did QA withhold the alerts?** The digest still sends, with a banner. This
   is working as designed, not a fault — report what was withheld and why.
4. **Were there simply no deals, with `ALWAYS_EMAIL` off?** Then no email is
   correct behaviour.
