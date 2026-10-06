# AGENTS.md — cheapflightstracker
<!-- standard: 1.1.2 · tier: minimal · ui: no · db: no · verified: 2026-10-06 -->

## 1. What this is
- A daily job scrapes KL→Indonesia fares, decides which are unusually cheap, and emails a digest to its owner.
- It runs unattended on GitHub Actions and nobody reads the logs. Live today: the daily digest, plus a far-horizon scan, a liveness watchdog and a destination probe.
- Read this before changing anything in `flightdeals/` or `.github/workflows/`.
- The one thing to understand: every defect that has shipped produced a plausible-looking email (on time, readable, wrong), never a crash. Tests were green for all of them, so "the tests pass" is not evidence a change is correct (lessons L-01 to L-16).

## 2. Stack and commands
- Runtime and package manager: Python 3.10+ (CI runs 3.10 and 3.11), `pip` with `requirements.txt`.
- Install: `pip install -r requirements.txt`
- Test: `python3 -m unittest discover -s tests` (necessary, nowhere near sufficient)
- Replay audit: `python scripts/replay_audit.py --all` (re-runs recorded days through the independent auditor)
- Dry run: `python run.py --provider mock --dry-run`
- Full verification (the gate for "done"): `python3 -m unittest discover -s tests`, plus the replay audit when the detector, statistics, baselines or emailer change.

## 3. Read first, in this order (nothing else unless a brief cites it)
1. STATE.md — what is done, next, blocked
2. docs/lessons.md — every incident, the rule it produced, and where the rule lives
3. The current slice's docs/slices/<id>/brief.md

## 4. Boundaries
- Never: push to the default branch, read `.env*` or other secrets, force-push, reset --hard, rm -rf.
- Bot-owned, never hand-edit: `data/price_history.json`, `data/date_prices.json`, `data/alert_state.json`. They are the evidence the auditor uses to check the code; build fixtures inside the test instead.
- Secrets live in GitHub Secrets only. `.env` stays gitignored. Nothing secret goes in a file, a log line or a commit message.
- `qa/` never imports from `flightdeals/`.
- Stay inside the task named in the brief. Report a needed scope change; do not make it.

## 5. Where facts live
- Current state: STATE.md · Owner items: STATE.md §Owner items · Direction: STATE.md §Direction in force
- Lessons: docs/lessons.md · Runbook: docs/runbooks/digest.md · Research: docs/research/competitor-analysis.md
- Records (not reading): docs/records/ (full incident narrative: docs/records/postmortems.md)

## 6. Working rules
1. A baseline is built from daily-cheapest fares, never from every offer. (lesson L-02)
2. One-way and round-trip fares never share a baseline. (lesson L-01)
3. A baseline only ever uses observations from strictly before the run date; a fare must not help set the standard it is judged against. (lesson L-17)
4. Only a route's own cheapest fare is ever an alert candidate; scoring all 30 dates and keeping the best discount turns noise into a search. (lesson L-06)
5. No alert without an absolute floor: z-score alone is meaningless; every path also needs at least 12% off and at least MYR 40 saved. (lesson L-06)
6. The 30-day window is scanned exhaustively, never sampled; the far-horizon lane (`flightdeals/horizon.py`) is exhaustive within each 30-day block; windows are compared only when both clear 80% coverage; never merge their stores. (lessons L-03, L-18)
7. `MIN_SAMPLES` is a safety floor, not a tuning knob; lowering it to 1 alerted 21 of 26 routes off single junk readings. (lesson L-06)
8. Scheduled runs fire 115 to 196 minutes late, always; do not declare a run missing before 05:00 UTC (13:00 MYT) and do not trigger a manual run to "recover" it. (lesson L-08)
9. Check the timestamps of recent `schedule` runs before suspecting a deregistered cron; renaming the default branch can stop the cron until the next commit lands. (lesson L-08)
10. Verify your own edits applied: prefer real file edits over scripted replacement, `assert` the match count when scripting, and verify rendering changes with `grep -o | wc -l` on the rendered output, never `grep -c`. (lesson L-07)
11. "The tests pass" is not evidence of correctness; run the replay audit before every commit touching the detector, statistics, baselines or emailer, and treat a BLOCK as the change being wrong on real data. (lessons L-01 to L-16)
12. Do not "clean up" `qa/` by importing from `flightdeals/`: two independent derivations that agree is evidence, one implementation checking itself is not. (lesson L-19)
13. A check needs a test that reconstructs the failure it catches, and the clean-digest test must still pass. (lesson L-16)
14. Far-horizon blocks are anchored to the day the store was scanned (`scan_anchor()`), never to the digest date; a weekly scan read daily drifts off its own dates and the section silently vanishes. (lesson L-18)

## 7. How work is done here
- Tier: minimal.
- Merge only through a pull request whose CI passed on that exact commit; pull requests target the default branch, `claude/cheapflightstracker`.
- Done means: `python3 -m unittest discover -s tests` exits 0 at the final commit (plus `python scripts/replay_audit.py --all` when the detector, statistics, baselines or emailer change), and STATE.md is updated.
- Lint: `bun .standard/standard-check.mjs .` must exit 0 (CI job `standard-check`).

## 8. Repo map
| Path | What it does |
|------|--------------|
| `flightdeals/` | the service: config, search, baseline, detector, emailer |
| `qa/` | the independent auditor; must not import `flightdeals` |
| `scripts/replay_audit.py` | replay recorded days past the auditor |
| `scripts/check_liveness.py` | did the job run at all? |
| `scripts/price_lookup.py` | what have we ever seen for a route? (`--all` for every route) |
| `tests/` | unit tests (`python3 -m unittest discover -s tests`) |
| `data/` | bot-owned price history and alert state |
| `docs/lessons.md` | every incident, the rule it produced, where the rule lives |
| `docs/runbooks/digest.md` | what to do when the digest looks wrong or stops |
| `docs/research/competitor-analysis.md` | industry techniques surveyed, with a verdict on each |
| `docs/records/postmortems.md` | the full incident narrative |
| `.github/workflows/` | CI plus five scheduled workflows (daily alerts, horizon scan, liveness, destination probe, send preview) |
