---
name: verify-release
description: Run the full pre-ship verification for Cheap Flights Tracker — unit tests, offline pipeline smoke test, replay of every recorded day past the independent auditor, and the render-count check for email changes. Use before committing or pushing any change to flightdeals/, qa/, scripts/ or .github/workflows/, and whenever asked to check that the service still works.
---

# Verify a release

The gate this project needs, in the order that catches the most.

Do not stop at the first green step. Step 1 has been green for every bug that
ever shipped here.

## 1. Unit tests — the floor

```bash
python -m unittest discover -s tests
```

Necessary, and nowhere near sufficient. Passing means nothing crashed.

## 2. Whole pipeline, no network

```bash
python run.py --provider mock --dry-run
```

Exercises search → baseline → detector → QA gate → both email bodies. This has
caught more real breakage than any single unit test, because it runs the wiring
rather than the pieces.

## 3. Replay every recorded day past the auditor — the real gate

```bash
python scripts/replay_audit.py --all
```

Re-runs past days against real history and audits each resulting digest with an
independently written implementation of the statistics.

- **BLOCK** — the change would have sent a wrong email on a day that really
  happened. Fix it; do not rationalise it.
- **WARN** — read it. `D3` on the earliest recorded day is expected (routes were
  added after tracking began) and is the one warning that is usually noise.
- **clean** — the change agrees with an independent derivation on every day on
  record.

## 4. If the change touches the email, count the rendering

Two attempts to add map links were made with scripted replacements that matched
nothing, silently succeeded, and shipped nothing. The tests passed throughout.
A passing test is not evidence that an edit landed — **counting the output is.**

```bash
python run.py --provider mock --dry-run >/dev/null
grep -o "maps/search" artifacts/digest.html | wc -l
```

The run writes the rendered digest to `artifacts/digest.html`. Expect one link
per route row plus one per deal card. Zero, or an unchanged count, means the
edit did not apply.

Note `grep -o | wc -l`, not `grep -c`: the latter counts *lines* containing a
match, and this template puts several links on one line — it reported 23 where
the true count was 48.

## 5. If the change touches a workflow

- Renaming a branch or editing `on:` can deregister a `schedule:` trigger.
  GitHub re-registers on push to the default branch — so land a commit and then
  confirm a `schedule` run actually appears the next morning.
- Confirm `python scripts/check_liveness.py` still exits 0.

## Reporting back

State what you ran and what it said. If everything is clean, say so in two
lines. If the replay blocked, lead with the day and the finding — that is the
whole message, and it should not be buried under a summary of the diff.

Never report a change as verified when only step 1 was run. Say which steps ran
and which did not.
