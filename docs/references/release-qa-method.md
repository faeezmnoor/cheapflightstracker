<!-- layer: knowledge · status: living · verified: 2026-11-11 -->
# Release QA: incident history and new checks

Moved verbatim from .claude/agents/release-qa.md (harness audit 2026-11); the agent reads it when it applies.

## Review against the incident history

`docs/records/postmortems.md` is the authoritative list. Every entry is a real failure,
and each names the check that now guards it. For any diff, ask which of these
it could reintroduce:

| Failure mode | What to look for in the diff |
|---|---|
| Baseline pooling | anything that stops keying baselines on `(route, trip_type)` |
| Baseline from all offers | anything that skips the reduce-to-daily-cheapest step |
| Lookahead | history filtered with `<=` rather than `<` the run date |
| Candidate selection | scoring many dates and keeping the best discount, instead of the route's single cheapest fare |
| Threshold erosion | lowering `MIN_SAMPLES`, `MIN_DATE_SAMPLES`, or removing an absolute floor so a z-score can qualify alone |
| Sampled dates | anything that shrinks `departure_offsets` from the full window |
| Silent no-op edit | scripted string replacement with no match assertion |
| Schedule deregistration | renaming a branch, or changing `on:` in a workflow |
| Auditor capture | `qa/` importing from `flightdeals/` — this destroys the independence the package exists for |

That last one deserves a hard stop. If a change makes the auditor import the
code it audits, reject it regardless of how much duplication it removes.

## Judging new checks

If the diff adds an auditor check, it must come with a test that reconstructs a
failure the check catches **and** the clean-digest test must still pass. A
checker with no demonstrated catch is untested code in the highest-trust
position in the system; a checker that fires on good digests gets switched off
within a week and then guards nothing.
