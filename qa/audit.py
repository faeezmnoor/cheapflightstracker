"""CLI: audit a digest against the history it was built from.

    python -m qa.audit --digest artifacts/digest.json \
                       --history data/price_history.json \
                       --html artifacts/digest.html

Exit codes: 0 clean, 1 warnings only, 2 blocking findings. CI distinguishes
the last two — a warning is a thing to look at, a blocking finding means the
email was, or would have been, actively wrong.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional

from .checks import audit, summarise_checks
from .findings import AuditReport


def load_history(path: str) -> List[dict]:
    """Read the history file, tolerating both storage shapes it has had."""
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    if isinstance(raw, dict):
        return raw.get("observations") or []
    return raw or []


def load_json(path: Optional[str]) -> Optional[dict]:
    if not path or not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_text(path: Optional[str]) -> Optional[str]:
    if not path or not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def write_markdown_summary(report: AuditReport, path: str) -> None:
    """Append a table to GITHUB_STEP_SUMMARY so failures are visible without
    opening the logs — a check nobody reads is a check that does not exist."""
    lines = ["## Digest QA", ""]
    if not report.findings:
        lines.append(f"All {len(report.checks_run)} checks passed.")
    else:
        lines += ["| Severity | Check | Route | Finding |",
                  "|---|---|---|---|"]
        for f in report.findings:
            detail = f.message + (f" — {f.evidence}" if f.evidence else "")
            lines.append(f"| {f.severity.upper()} | {f.check} | "
                         f"{f.route_key or '—'} | {detail} |")
    lines += ["", "<details><summary>Checks run</summary>", ""]
    purposes = summarise_checks()
    for check in report.checks_run:
        lines.append(f"- `{check}` — {purposes.get(check, '')}")
    lines += ["", "</details>", ""]
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Audit a flight-deals digest")
    parser.add_argument("--digest", required=True,
                        help="digest payload JSON written by the report step")
    parser.add_argument("--history", default="data/price_history.json",
                        help="price history as the detector saw it")
    parser.add_argument("--html", help="rendered digest, for presentation checks")
    parser.add_argument("--continuity-window", type=int, default=7)
    parser.add_argument("--warn-only", action="store_true",
                        help="report blocking findings but exit 0 (advisory mode)")
    parser.add_argument("--strict", action="store_true",
                        help="fail on warnings too — for pre-merge gates, not "
                             "for the daily run, which would go red on routine "
                             "data-quality noise and stop being read")
    args = parser.parse_args(argv)

    digest = load_json(args.digest)
    if digest is None:
        print(f"[qa] no digest at {args.digest} — nothing to audit",
              file=sys.stderr)
        return 2

    report = audit(digest, load_history(args.history), load_text(args.html),
                   continuity_window=args.continuity_window)
    print(report.render())

    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        write_markdown_summary(report, step_summary)

    if report.blocking:
        return 0 if args.warn_only else 2
    if report.findings and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
