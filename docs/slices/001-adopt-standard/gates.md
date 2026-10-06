<!-- layer: records · status: living (while open) · verified: 2026-10-06 -->
# 001 · adopt-standard — gate ledger
| Gate | CHECK | EXPECT | EVIDENCE |
| --- | --- | --- | --- |
| G1 | `bun .standard/standard-check.mjs .` | exit 0 | |
| G2 | `sh -c "python3 -m unittest discover -s tests 2>&1 \| grep -q '^OK'"` | exit 0 | |
| G3 | `sh -c "! grep -rIl -e /Us[e]rs/ -e /ho[m]e/ AGENTS.md CLAUDE.md STATE.md docs .github"` | exit 0 | |
| G4 | `sh -c "! grep -rIl -i fa[e]ez AGENTS.md CLAUDE.md STATE.md docs/slices docs/lessons.md .github"` | exit 0 | |
| G5 | `sh -c "test ! -e docs/POSTMORTEMS.md && test -e docs/records/postmortems.md && test -e docs/runbooks/digest.md && test -e docs/lessons.md"` | exit 0 | |
