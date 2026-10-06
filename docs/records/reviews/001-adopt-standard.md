<!-- layer: records · status: record · verified: 2026-10-06 -->
# Review: 001 adopt-standard

Independent review of branch slice/001-adopt-standard against claude/cheapflightstracker (correctness, nothing-lost, public-hygiene, cold-start).

## Cold start (AGENTS.md and STATE.md only)
- Live: the daily digest on GitHub Actions (plus horizon scan, liveness, destination probe); scheduled runs fire 115 to 196 minutes after the 01:00 UTC cron.
- Next: nothing planned; slice 001 is built but not merged.
- Waits on the owner: nothing (Owner items: None). Sufficient to resume; the unresolved stale paths are in Blocked.

## Nothing lost: checklist (all ticked)
- Standing rule (plausible-looking email, tests green): AGENTS.md section 1 and rule 11; full text in docs/lessons.md.
- Invariants 1 to 7: AGENTS.md section 6 rules 1 to 7; verbatim with reasons in docs/lessons.md. Numbers kept: 12%, MYR 40, 80% coverage, 21 of 26 routes. Coverage figures (50% about 12% high, 80% about 3.6%, 10 of 30 dates, 41%, 13.9%) are in lessons.md.
- Data-file rule: AGENTS.md section 4; verbatim in lessons.md.
- Scheduled runs late (01:00 UTC, 02:55 to 04:16, 115 to 196 minutes, 05:00 UTC / 13:00 MYT, 13 Aug incident, default-branch hazard): rules 8 and 9; verbatim in lessons.md.
- Verify-your-edits with the grep -o | wc -l advice and the grep -c warning: rule 10; verbatim including the code block.
- Secrets: AGENTS.md section 4; verbatim in lessons.md.
- qa/ independence: section 4 and rule 12; verbatim in lessons.md.
- "Where things are" table: AGENTS.md section 8 (extended, paths updated).
- Moves intact: the diffs of postmortems, runbook and competitor analysis show only the added header line.

## Public hygiene
- No person's name, absolute home path or internal link in the added lines.
- flightdeals/, qa/, scripts/, run.py, tests/, data/, requirements.txt, LICENSE, .claude/ and the five scheduled workflows: no changes in the range.
- ci.yml: only the new standard-check job is added (name standard-check, runs the lint command). The parsed jobs are test, audit-replay, standard-check.

## Dead links after the moves (old to new)
- docs/records/postmortems.md line 109: docs/RUNBOOK.md to docs/runbooks/digest.md (missing from the builder's STATE.md list).
- docs/runbooks/digest.md lines 82 and 125: docs/POSTMORTEMS.md to docs/records/postmortems.md.
- .github/workflows/liveness.yml line 13 (comment): docs/RUNBOOK.md to docs/runbooks/digest.md.
- .claude/agents/release-qa.md line 49: docs/POSTMORTEMS.md to docs/records/postmortems.md.
- Stale in meaning, link still resolves: README.md line 231 says CLAUDE.md carries the invariants (they now live in AGENTS.md and docs/lessons.md); .claude/agents/digest-auditor.md line 99 and docs/records/postmortems.md lines 90 and 109 name CLAUDE.md for the invariants and the delay note.
- README image path docs/assets/digest-preview.png resolves.

## Structure checks
- AGENTS.md 69 lines, eight sections plus header, header fields correct, no Claude-only terms (the only match is the default branch name). CLAUDE.md 4 lines, starts with @AGENTS.md. STATE.md 27 lines; the verified line names a branch commit and was written with a passing lint and test run.

## Gates (as written in gates.md)
- G1 lint: exit 0, 0 FAIL 0 WARN. G2 unittest: OK. G3: pass. G4: pass. G5: pass.

## Planted defects (restored afterwards; tree clean)
- Invariant 5 removed from AGENTS.md section 6: survived (lint exit 0, no gate fails). The lint does not check rule content.
- A personal name added to docs/lessons.md: caught by G4 only; the lint passed.
- Header removed from docs/records/postmortems.md: survived (lint exit 0, no gate checks it).

## Not checked
- CI behaviour on a real runner; replay audit; vendored lint source beyond reading its rule list.

VERDICT: APPROVE
