"""Independent quality assurance for the daily digest.

This package deliberately does **not** import from ``flightdeals``. Its job is
to check that package's output, and a checker that reuses the code under test
inherits its bugs — every historical defect in this project produced a digest
that looked entirely reasonable, so "it ran without error" proves nothing.

The auditor therefore re-derives the numbers from the raw price history with a
second, separately written implementation and compares them against what the
email actually claims. Where the two disagree, one of them is wrong, and that
is worth an alarm either way.
"""

from .findings import BLOCK, INFO, WARN, Finding, worst_severity

__all__ = ["Finding", "BLOCK", "WARN", "INFO", "worst_severity"]
