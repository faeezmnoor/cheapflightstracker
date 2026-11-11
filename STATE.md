# STATE — cheapflightstracker
<!-- layer: state · status: living · budget: 80 lines -->
verified: 2026-10-06 at ccb73b7 by CI on PR #3 (test 3.10 and 3.11, audit-replay, standard-check all green) and the reviewer cold-start test (pass)

## Now
- Standard 1.6.0 re-applied 2026-11-11 (lint bundle, declared version, harness-audit line in the AGENTS.md header, runbook sections, specialists trimmed into docs/references/, public-address declaration in docs/workflow.md); local audit in docs/records/audit-2026-11.md. Pending the pull request.
- The service is NOT healthy: the newest price observation is 2026-10-06, 35 days old at 2026-11-10. The data-commit step of the daily and horizon workflows is rejected by branch protection on the default branch (`GH006: Protected branch update failed`), and the liveness watchdog has failed on every run since (14 failures in the last 30 runs). Of the last 14 daily runs, 6 failed and 7 succeeded; the successes also cannot persist their data. Read from `gh run list` on 2026-11-11.
- The daily digest still runs on GitHub Actions; scheduled runs fire 115 to 196 minutes after the 01:00 UTC cron (docs/lessons.md L-08).

## Next
- Owner ruling on how the bot may commit data (see Owner items); then a slice to apply it and confirm a scheduled run lands data.

## Blocked
- Bot data commits rejected by branch protection (above). Not fixed here: it is a repository setting and workflow change.
- Stale path references left in place by the path-only scope: `.github/workflows/liveness.yml` line 13 still names docs/POSTMORTEMS.md or docs/RUNBOOK.md (workflow code, out of scope for a documentation pass).

## Direction in force
- Public portfolio repository under the MIT licence. The default branch is `claude/cheapflightstracker`, not main; scheduled workflows register against it.

## Owner items
1. Choose how the data-commit bot gets past branch protection on the default branch: allow the Actions bot to bypass the rule, push data to a separate unprotected branch, or relax the rule for `data/`. Until then no new fare history is kept and the liveness watchdog opens an issue every day.

## Measurements
| Slice | Builder tokens | Reviewer tokens | Fix rounds |
| --- | --- | --- | --- |
| 001-adopt-standard | ~90k + ~71k (build, rebase-and-carry) | ~78k | 0 (path fixes only) |
Owner minutes this week: 0. Last cold-start test: 2026-10-06, pass (independent reviewer); not re-run in the 1.6.0 re-apply.
