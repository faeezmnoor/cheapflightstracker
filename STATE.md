# STATE — cheapflightstracker
<!-- layer: state · status: living · budget: 80 lines -->
verified: 2026-11-12 at 572fc47 by gh api (branch protection, rulesets, deploy keys, secrets list), git log on the default branch (last bot commit 2026-10-06), the unit tests

## Now
- Standard 1.6.0 re-applied 2026-11-11 (lint bundle, declared version, harness-audit line in the AGENTS.md header, runbook sections, specialists trimmed into docs/references/, public-address declaration in docs/workflow.md); local audit in docs/records/audit-2026-11.md. Pending the pull request.
- The service saved no fare history from 2026-10-06 to 2026-11-12: the October branch protection rejected the workflows' data commits (lesson L-22). Fix ruled by the owner on 2026-11-12: the daily and horizon workflows push with a deploy key (secret `DATA_DEPLOY_KEY`), and a branch ruleset keeps the four required checks for pull requests while letting that key through. Not yet confirmed healthy: confirm at the first scheduled run after the ruleset is active (a `flight-deals-bot` commit lands and the liveness watchdog passes).
- The daily digest still runs on GitHub Actions; scheduled runs fire 115 to 196 minutes after the 01:00 UTC cron (docs/lessons.md L-08).

## Next
- Owner ruling on how the bot may commit data (see Owner items); then a slice to apply it and confirm a scheduled run lands data.

## Blocked
- Until the ruleset replaces the old protection rule (the step after this pull request merges), data commits are still rejected.
- Stale path references left in place by the path-only scope: `.github/workflows/liveness.yml` line 13 still names docs/POSTMORTEMS.md or docs/RUNBOOK.md (workflow code, out of scope for a documentation pass).

- `python3 scripts/replay_audit.py --all` exits 2 on recorded data, identically before and after this change: 2026-09-26 is a BLOCK (C2, 8 alerts on 26 routes) in the recorded history. AGENTS.md makes it required only when the detector, statistics, baselines or emailer change; the owner decides whether to keep that day as a known case.

## Direction in force
- Public portfolio repository under the MIT licence. The default branch is `claude/cheapflightstracker`, not main; scheduled workflows register against it.

## Owner items
1. Ruled 2026-11-12 (keep the required checks, let the data commits through). Nothing to do unless the first scheduled run after the change still saves nothing.

## Measurements
| Slice | Builder tokens | Reviewer tokens | Fix rounds |
| --- | --- | --- | --- |
| 001-adopt-standard | ~90k + ~71k (build, rebase-and-carry) | ~78k | 0 (path fixes only) |
Owner minutes this week: 0. Last cold-start test: 2026-10-06, pass (independent reviewer); not re-run in the 1.6.0 re-apply.
