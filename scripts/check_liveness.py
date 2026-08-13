#!/usr/bin/env python3
"""Has the service actually produced data recently?

Deliberately dependency-free and separate from the pipeline: it reads the
committed history file and nothing else, so it still gives a straight answer
when the scanner, the provider or the emailer is broken.

    python scripts/check_liveness.py --max-age-hours 30

Exit 0 if fresh, 1 if stale or empty.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from typing import List, Optional


def observation_days(path: str) -> List[str]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    records = raw.get("observations", []) if isinstance(raw, dict) else (raw or [])
    return sorted({r["observed_date"] for r in records if r.get("observed_date")})


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", default="data/price_history.json")
    # Observations carry a date, not a timestamp, so staleness is counted in
    # whole days. The default of 0 means "today's run must have landed" — the
    # watchdog is scheduled well after the digest, so anything less is a miss.
    #
    # An earlier version of this script measured hours from the end of the last
    # observed day. It would have passed cleanly on the very morning it was
    # written to catch: at 03:00 UTC with yesterday's data as the newest, that
    # arithmetic gives an age of three hours, not a missed run.
    parser.add_argument("--max-age-days", type=int, default=0,
                        help="how many whole days behind today is tolerable")
    args = parser.parse_args(argv)

    days = observation_days(args.history)
    if not days:
        print(f"[liveness] FAIL — no observations in {args.history}")
        return 1

    latest = date.fromisoformat(days[-1])
    today = datetime.now(timezone.utc).date()
    behind = (today - latest).days

    print(f"[liveness] latest observation {days[-1]} "
          f"({behind} day(s) behind {today}, {len(days)} day(s) on record)")
    if behind > args.max_age_days:
        print(f"[liveness] FAIL — no data for {behind} day(s). "
              f"Check the Actions tab for a missing scheduled run: a renamed "
              f"default branch silently deregisters the cron.")
        return 1
    print("[liveness] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
