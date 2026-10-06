# STATE — cheapflightstracker
<!-- layer: state · status: living · budget: 80 lines -->
verified: 2026-10-06 at bf18c71 by unittest OK (125 tests), bun .standard/standard-check.mjs . (0 FAIL), gates G3-G5 (exit 0), reviewer cold-start (pass)

## Now
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
<!-- filled by the orchestrator at CLOSE from the harness figures; builders leave this table alone -->
| Slice | Builder tokens | Reviewer tokens | Fix rounds |
| --- | --- | --- | --- |
| 001-adopt-standard | | | |
Owner minutes this week: . Last cold-start test: .
