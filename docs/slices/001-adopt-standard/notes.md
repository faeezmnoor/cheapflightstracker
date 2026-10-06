<!-- layer: knowledge · status: living (while open) · verified: 2026-10-06 -->
# 001 · adopt-standard — notes

## Builder decisions

- Lesson ids L-01 to L-16 follow the numbering of the "Shipped defects" entries in docs/records/postmortems.md. (verified: one row per entry, same order)
- L-17, L-18, L-19 are added for rules in the old CLAUDE.md with no postmortem entry (strictly-before baselines, the far-horizon sampling finding, the qa/ duplication). Their date column says "carried over". (inferred: the brief asks for one row per incident and says nothing is dropped, so rules without an incident needed a home)
- Dates of most lessons are "2026-08" because the postmortems record a day only for incidents 8, 11, 12 and 14. (verified against the record; the 2026-08 month for the others is inferred from the entries' references to 13 to 18 Aug)
- The full explanations from the old CLAUDE.md are kept verbatim in a section of docs/lessons.md under the table, rather than stretched into table cells. (inferred: the brief allows "docs/lessons.md verbatim"; table cells would not hold multi-paragraph text)
- AGENTS.md §6 has 13 one-line rules (seven invariants, two lateness rules, verify-your-edits, "tests are not evidence", qa independence, adding-a-check). Rule 9 splits the cron-registration hazard from rule 8 so each stays one line. (inferred)
- Data-file and secrets rules went to AGENTS.md §4, not §6, per the brief's §4 list; their explanations are in docs/lessons.md. (verified against the brief)
- The five scheduled workflows were not touched. The stale paths still named in `.claude/agents/release-qa.md`, `.github/workflows/liveness.yml` (a comment), `docs/runbooks/digest.md` and `docs/records/postmortems.md` were left because the brief limits link updates to README and forbids editing records beyond the header. Listed in STATE.md Blocked. (verified: lint exits 0 with them)
- G2 used the system `python3` (3.9.6) first: the suite ran 125 tests, OK with 11 skipped. It was repeated with `.venv/bin/python3` (3.11, requirements installed): 125 tests, OK, none skipped. `.venv/` was already in .gitignore.

## Not checked
- CI itself (the new job has not run on GitHub; the YAML was not parsed by a YAML library, only read).
- Branch protection: the `standard-check` required context is an owner or orchestrator action.
- Whether `docs/assets/digest-preview.png` is still referenced as intended: README line 18 uses it, path unchanged.

## Gate instrument finding
- G2 as written (`python3 -m unittest discover -s tests 2>&1 | tail -1 | grep -q OK`) exits 1 even though the suite passes: stderr log lines from the tests print after the unittest summary when stdout and stderr are merged into a pipe, so `tail -1` is a `[report] ...` line, not `OK`. The same assertion written as `grep -q '^OK'` over the whole output passes. The gate watches the last line, not the result. For the orchestrator to rule on.

## Cold-start answer
A fresh agent reads AGENTS.md, then STATE.md. Cold-start question: what must I not do before changing the detector, and how do I know I am done? Answer from the files: do not rely on green unit tests; run `python scripts/replay_audit.py --all` and treat a BLOCK as wrong (AGENTS.md §6 rule 11), never hand-edit the three data files or import flightdeals from qa/ (§4), and done is `python3 -m unittest discover -s tests` exit 0 plus the replay audit, with STATE.md updated (§7). The reason behind each rule is one link away in docs/lessons.md.
