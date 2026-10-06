<!-- layer: knowledge · status: living (while open) · verified: 2026-10-06 · budget: 200 lines -->
# 001 · adopt-standard — brief (context pack)
Source: the house standard ($STANDARD_DIR/STANDARD.md) §3, §4 Minimal, §6, §7, §12, §13 (Minimal steps 2, 3, 4, 9, 10, 12, 13); lessons L-04 to L-15. Templates: $STANDARD_DIR/templates/.

Goal: conform this public Python repository (an unattended daily job on GitHub Actions) to the house standard at Minimal tier (UI: no, DB: no) without losing one line of the hard-won operational knowledge in its CLAUDE.md, RUNBOOK and POSTMORTEMS, so that `bun .standard/standard-check.mjs .` exits 0 and a fresh agent resumes it cold.
Default branch: `claude/cheapflightstracker` (not main). Work on branch slice/001-adopt-standard (created); pull requests target the default branch.
In scope:
- AGENTS.md (≤ 150 lines, header `standard: 1.1.2 · tier: minimal · ui: no · db: no · verified: <date>`), built from the current CLAUDE.md: §1 what it is; §2 stack and commands (Python 3, requirements.txt; test `python3 -m unittest discover -s tests`; replay `python scripts/replay_audit.py --all`; dry run `python run.py --provider mock --dry-run`; full verification = the unittest command); §3 read-first; §4 boundaries (bot-owned data files never hand-edited; secrets only in GitHub Secrets; `qa/` never imports `flightdeals/`); §5 where facts live; §6 working rules = the seven invariants plus the "scheduled runs run late" rule, "verify your own edits" rule and the plausible-email rule, each as ONE line (link to docs/lessons.md L-ids); §7 how work is done (tier minimal; PR with CI green; done = unittest exit 0 and replay audit when the detector, statistics, baselines or emailer change); §8 repo map (the existing "Where things are" table). Where a rule's explanation does not fit one line, the explanation moves verbatim into docs/lessons.md as that lesson's "What happened" and "The rule"; nothing is dropped.
- CLAUDE.md → `@AGENTS.md` plus at most 20 lines (the replay-audit reminder may stay as one line).
- STATE.md (≤ 80 lines): Now (live: the daily digest on GitHub Actions; CI badge; last known behaviour per CLAUDE.md: scheduled runs fire 115–196 minutes late), Next (nothing planned), Blocked (nothing), Owner items (none, or anything you find), Direction (public portfolio repo under MIT; default branch is claude/cheapflightstracker), Measurements (leave the table for the orchestrator).
- docs/lessons.md from the template, populated from docs/POSTMORTEMS.md: one row per incident (L-01…): date, what happened (one or two sentences), cost, the rule, where the rule lives (AGENTS.md §6 line or the check in qa/ or scripts/ that now catches it). The full POSTMORTEMS.md narrative moves to docs/records/postmortems.md with the records header (git mv, then edit nothing else in it).
- docs/RUNBOOK.md → docs/runbooks/digest.md (git mv; add the one-line header; keep content; do not restructure).
- docs/COMPETITOR-ANALYSIS.md → docs/research/competitor-analysis.md (git mv; header).
- docs/assets/ stays (README uses the image? check; if README links it, keep the path).
- README.md: path-only link updates for any moved file (L-12); no other README change.
- CI: in .github/workflows/ci.yml add a job `standard-check` with `name: standard-check` (setup Bun, `bun .standard/standard-check.mjs .`); do not touch the scheduled workflows (daily-flight-alerts, horizon-scan, liveness, probe-destinations, send-preview) in any way.
- .claude/agents (digest-auditor 100 lines, release-qa 84) and .claude/skills/verify-release stay as they are; note in STATE.md Blocked: "specialist agents exceed the 80-line budget; trim when the Agents lint group arrives".
- notes.md: Builder decisions (verified/inferred), not checked, and your own cold-start answer.
Out of scope: flightdeals/, qa/, scripts/, run.py, tests/, data/, requirements.txt, the scheduled workflows, LICENSE.
Stop if: the lint demands a file this brief forbids; the unittest command fails for reasons unrelated to your changes (install dependencies in a local virtualenv under .venv/ first if needed; .venv is gitignored? check .gitignore and add `.venv/` if missing); anything would put a person's name or an absolute home path into a committed file.

## Rules that apply (copied in, with source)
- Public repository: no person's name, no absolute home path, no internal links (§1; H1; L-05, L-09). Pre-existing names in moved records stay as they are (owner decision pending).
- Nothing is deleted; moves via git mv with headers (§12; Goal 6).
- Every docs/ file carries the one-line header, records included (L-11).
- The verified line is written last and names the head (L-10). The verification command is a gate (L-08).
- Path-only link fixes in README are in scope (L-12). The lint job is named standard-check (L-15).

## Files to read (only these)
- $STANDARD_DIR/STANDARD.md §6, §7, §12, §13; $STANDARD_DIR/templates/{AGENTS.md,CLAUDE.md,STATE.md,docs/lessons.md,.github-ci-minimal.yml}
- CLAUDE.md, docs/POSTMORTEMS.md, docs/RUNBOOK.md (first 20 lines), README.md (links only), .github/workflows/ci.yml, .gitignore, .claude/agents/*.md (line counts only)

## Decisions already made (do not reopen)
- Tier Minimal, UI no, DB no (0001). Lessons register shape (0008). Sequential migration with LEARN (0009).

## Report
Fixed format, under 300 words: Verdict · Commits · Gates met/total · Findings (for LEARN) · Decisions (verified/inferred) · Needs the owner.
