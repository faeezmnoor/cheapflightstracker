"""What the auditor reports, and how loudly."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List

# Severity ladder. "block" is reserved for things that make the digest
# actively misleading — a wrong price, an alert built on one observation. Those
# suppress the alerts rather than the whole email: the cheapest-today table is
# still useful when the *statistics* are untrustworthy.
BLOCK = "block"
WARN = "warn"
INFO = "info"

_RANK = {INFO: 0, WARN: 1, BLOCK: 2}


@dataclass
class Finding:
    """One failed (or noteworthy) check."""

    check: str                 # stable id, e.g. "C1" — greppable in CI logs
    severity: str              # BLOCK | WARN | INFO
    message: str               # one line, human first
    evidence: str = ""         # the numbers that justify it
    route_key: str = ""        # which route, when it is route-specific

    @property
    def blocks(self) -> bool:
        return self.severity == BLOCK

    @property
    def about_data(self) -> bool:
        """True when this describes the recorded data rather than the code.

        The distinction decides what may fail a push. "This change would render
        a wrong number" is a property of the diff and is reproducible; "the
        provider returned 67% of the window today" is a property of the world,
        and can flip a build red or green with no code change at all. Gating
        pushes on the second teaches everyone to ignore the first.

        The `D` prefix has always meant a data check; this makes the meaning
        load-bearing rather than a naming convention.
        """
        return self.check.startswith("D")

    def render(self) -> str:
        where = f" [{self.route_key}]" if self.route_key else ""
        detail = f"\n        {self.evidence}" if self.evidence else ""
        return f"{self.severity.upper():5} {self.check}{where}: {self.message}{detail}"


@dataclass
class AuditReport:
    findings: List[Finding] = field(default_factory=list)
    checks_run: List[str] = field(default_factory=list)

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    def ran(self, check: str) -> None:
        if check not in self.checks_run:
            self.checks_run.append(check)

    @property
    def blocking(self) -> List[Finding]:
        return [f for f in self.findings if f.blocks]

    @property
    def ok(self) -> bool:
        return not self.blocking

    def render(self) -> str:
        if not self.findings:
            return (f"QA: {len(self.checks_run)} checks passed "
                    f"({', '.join(self.checks_run)})")
        lines = [f"QA: {len(self.checks_run)} checks run, "
                 f"{len(self.findings)} finding(s), "
                 f"{len(self.blocking)} blocking"]
        # Loudest first — a blocking finding must not scroll off behind
        # a dozen informational ones.
        for f in sorted(self.findings, key=lambda f: -_RANK.get(f.severity, 0)):
            lines.append("  " + f.render())
        return "\n".join(lines)


def worst_severity(findings: Iterable[Finding]) -> str:
    return max((f.severity for f in findings), key=lambda s: _RANK.get(s, 0),
               default=INFO)
