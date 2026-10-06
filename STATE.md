# STATE — cheapflightstracker
<!-- layer: state · status: living · budget: 80 lines -->
verified: 2026-10-06 at ccb73b7 by CI on PR #3 (test 3.10 and 3.11, audit-replay, standard-check all green) and the reviewer cold-start test (pass)

## Now
- Adopted the house standard at Minimal tier (PR #3, merged 2026-10-06): AGENTS.md carries every invariant; lessons register and records; CI lint required on the default branch.
- Live: the daily digest runs on GitHub Actions (CI badge in README.md); last known behaviour: scheduled runs fire 115 to 196 minutes after the 01:00 UTC cron, never on time (docs/lessons.md L-08).
- Built, not merged: slice 001-adopt-standard (branch slice/001-adopt-standard): AGENTS.md, lessons register, moved docs, standard-check CI job.

## Next
Nothing planned.

## Blocked
- Specialist agents exceed the 80-line budget (.claude/agents/digest-auditor.md 100 lines, release-qa.md 84); trim when the Agents lint group arrives.
- Stale path references left in place by the path-only scope: `.claude/agents/release-qa.md` line 49, `.github/workflows/liveness.yml` line 13 and `docs/runbooks/digest.md` lines 82 and 125 still name docs/POSTMORTEMS.md or docs/RUNBOOK.md.

## Direction in force
- Public portfolio repository under the MIT licence. The default branch is `claude/cheapflightstracker`, not main; scheduled workflows register against it.

## Owner items
None.

## Measurements
| Slice | Builder tokens | Reviewer tokens | Fix rounds |
| --- | --- | --- | --- |
| 001-adopt-standard | ~90k + ~71k (build, rebase-and-carry) | ~78k | 0 (path fixes only) |
Owner minutes this week: 0. Last cold-start test: 2026-10-06, pass (independent reviewer).
