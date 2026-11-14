# STATE — cheapflightstracker
<!-- layer: state · status: living · budget: 80 lines -->
verified: 2026-11-14 at efe46d6 by git log on the default branch (bot commit efe46d6, 2026-11-13 08:11 UTC), gh run list (daily run 2026-11-13 success; liveness watchdog 2026-11-13 success), gh api (ruleset active, classic protection absent)

## Now
- Standard 1.6.0 re-applied 2026-11-11 (pull request 5): lint bundle, declared version, harness-audit line, runbook sections, specialists trimmed into docs/references/; local audit in docs/records/audit-2026-11.md.
- Data commits work again. The service saved no fare history from 2026-10-06 to 2026-11-12 because the October branch protection rejected the workflows' data commits (lesson L-22). Since pull request 6 (2026-11-12) the daily and horizon workflows push with a deploy key (secret `DATA_DEPLOY_KEY`) and a branch ruleset keeps the four required checks for pull requests while letting that key through. Confirmed on 2026-11-13: the scheduled daily run committed fare history (efe46d6) and the liveness watchdog passed. The five weeks of history are not recoverable.
- The daily digest still runs on GitHub Actions; scheduled runs fire 115 to 196 minutes after the 01:00 UTC cron (docs/lessons.md L-08).

## Next
- Nothing scheduled. Candidates: the stale path references below; the horizon workflow's first data commit under the deploy key is not yet observed (it uses the same checkout step).

## Blocked
- Stale path references left in place by the path-only scope: `.github/workflows/liveness.yml` line 13 still names docs/POSTMORTEMS.md or docs/RUNBOOK.md (workflow code, out of scope for a documentation pass).

- `python3 scripts/replay_audit.py --all` exits 2 on recorded data, identically before and after this change: 2026-09-26 is a BLOCK (C2, 8 alerts on 26 routes) in the recorded history. AGENTS.md makes it required only when the detector, statistics, baselines or emailer change; the owner decides whether to keep that day as a known case.

## Direction in force
- Public portfolio repository under the MIT licence. The default branch is `claude/cheapflightstracker`, not main; scheduled workflows register against it.

## Owner items
None. The 2026-11-12 ruling is applied and confirmed.

## Measurements
| Slice | Builder tokens | Reviewer tokens | Fix rounds |
| --- | --- | --- | --- |
| 001-adopt-standard | ~90k + ~71k (build, rebase-and-carry) | ~78k | 0 (path fixes only) |
Owner minutes this week: 0. Last cold-start test: 2026-10-06, pass (independent reviewer); not re-run in the 1.6.0 re-apply.
