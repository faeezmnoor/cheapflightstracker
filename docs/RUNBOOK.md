# Runbook

What to do when the digest misbehaves. Written so it works at 9am before
coffee, and so the diagnosis does not depend on remembering how the service is
put together.

---

## No email arrived

Check in this order. Stop at the first that explains it.

### 0. What time is it? (Do this first.)

The cron says 01:00 UTC but **every scheduled run this project has ever had
fired between 02:55 and 04:16 UTC** — 2 to 3 hours late. GitHub queues
scheduled workflows best-effort.

**Before 05:00 UTC (13:00 MYT), a missing digest is almost certainly just
late.** Wait. Triggering a manual run "to recover the day" is how 13 Aug
produced two contradictory emails 25 minutes apart.

### 1. Did the workflow run at all?

Actions tab → **Daily flight deals**. Look for today's run with event
`schedule`, and compare its timestamp against the last few days — the delay is
normal and consistent.

**No run listed, and it is past 05:00 UTC** — then the cron really did not
fire. Renaming the default branch deregisters `schedule:` triggers, and GitHub
only re-registers them on push. There is no failed run to inspect, because
there was no run.

```bash
# Get today's digest out now
#   Actions -> Daily flight deals -> Run workflow (leave dry_run unticked)
# Then re-register the schedule by landing any commit on the default branch.
```

Confirm the fix the next morning by checking a `schedule` run actually appears.
A manual run does **not** prove the cron is registered.

### 2. Did the run fail?

Open the run. The `scan` shards tolerate individual failures (`fail-fast:
false`) and `report` runs regardless, so a red scan shard does not by itself
explain a missing email.

If `report` failed, the logs say where. A failure in the send step means SMTP —
usually a revoked Gmail app password. Regenerate it and update the
`SMTP_APP_PASSWORD` secret.

### 3. Were there no deals?

With `ALWAYS_EMAIL` off, a morning with no qualifying fares sends nothing. That
is correct behaviour. Check the run log for `[report] flagged 0 deal(s)`.

### 4. Is the data actually landing?

```bash
python scripts/check_liveness.py
```

Exits non-zero if the history has stopped advancing. The watchdog runs this
daily at 06:00 UTC — well clear of the digest's 2-3 hour scheduling delay — and
opens an issue labelled `liveness` when it fails.

---

## The email looks wrong

### An alert seems too good, or contradicts the table

Replay that day and let the independent auditor judge it:

```bash
python scripts/replay_audit.py --date YYYY-MM-DD
```

A `BLOCK` names the problem directly. The checks and what each means are listed
in `docs/POSTMORTEMS.md`.

To see the exact email that was sent, download the `digest` artifact from that
day's run (30-day retention). It contains the rendered HTML and the payload the
auditor judged — enough to reproduce the decision without re-scraping.

### A price disagrees with Google Flights

In rough order of likelihood:

- **The date is outside the window.** Only the next 30 days are scanned.
- **Point of sale.** The runner asks for the Malaysian market; another market
  legitimately shows different prices.
- **A scrape that missed the cheap itineraries.** Around 7% of dates swing more
  than 2× day to day from this alone. Check whether neighbouring days agree
  before treating one reading as fact.
- **Time.** The digest is a morning snapshot; fares move.

### The email says "Alerts withheld by QA"

Working as designed. The digest was built, the auditor found something it could
not stand behind, and the alerts were suppressed while the cheapest-today table
was kept. The banner lists the reasons; the run's job summary has the detail.

This is not an outage — it is the gate doing its job. Investigate the finding,
not the suppression.

---

## Routine maintenance

### Before pushing any change

```bash
python -m unittest discover -s tests     # floor
python run.py --provider mock --dry-run  # whole pipeline, no network
python scripts/replay_audit.py --all     # the real gate
```

Or use the `verify-release` skill, which runs all of it and knows what the
warnings mean.

**Green unit tests are not evidence of correctness.** They were green for every
incident in `docs/POSTMORTEMS.md`.

### Adding a destination

```bash
# Confirm it is actually reachable before committing 30 searches a day to it
python scripts/probe_destinations.py
```

Add a curated Google Maps query in `DESTINATION_MAP_QUERIES` at the same time,
or the row falls back to a guess derived from the label.

### Reviewing thresholds

Worth doing once ~30 days of history have accumulated. Baselines tighten as
they thicken, so the same dip scores a larger z over time. Watch the alert rate
in the digest — `C2` blocks above 30% of routes, but drifting towards it is the
signal to retune rather than the moment to.

---

## What is deliberately not automated

- **Sending fewer emails on a quiet day.** Silence is indistinguishable from
  breakage, which is how several incidents ran for days.
- **Failing the daily run on warnings.** A job that is red every morning stops
  being read. Warnings go to the job summary; only blocking findings withhold
  alerts.
- **Auto-tuning thresholds.** Every incident involving thresholds came from
  loosening one to get more alerts.
