<!-- layer: knowledge · status: living (by decision) · verified: 2026-11-11 · budget: 120 lines -->
# Workflow — cheapflightstracker

Tier: minimal. The generic contract (stages, roles, review, gates, model tiers) is the house standard; this file declares only what is specific here.

## Cast
- Specialists (.claude/agents/): digest-auditor — investigates a delivered digest from recorded data; release-qa — independent QA review of a change before it ships
- Skill (.claude/skills/): verify-release — runs the unit tests, the dry run and the replay audit

## Project facts shared agents read
- Verification command: `python3 -m unittest discover -s tests` (plus `python scripts/replay_audit.py --all` when the detector, statistics, baselines or emailer change)
- References for the specialists: docs/references/digest-auditor-method.md, docs/references/release-qa-method.md

## Hygiene
- public-emails: [actions@github.com]  <!-- the GitHub Actions bot identity the workflows commit data files as; not a person's address -->
