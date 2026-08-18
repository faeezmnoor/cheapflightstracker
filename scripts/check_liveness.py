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


# Consecutive thin days before the watchdog speaks. One is noise.
STREAK_DAYS = 3


def recent_coverage(path: str, days: int) -> List[tuple]:
    """(day, share of route-dates that returned a price) for the last N days.

    Reads the per-departure-date store directly rather than importing the
    service, so it still answers when the pipeline itself is broken.
    """
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return []
    series = payload.get("series") if isinstance(payload, dict) else None
    if not isinstance(series, dict):
        return []

    seen: dict = {}
    routes, departures = set(), set()
    for key, by_day in series.items():
        if key.count("|") != 2:
            continue
        route, _, departure = key.split("|")
        routes.add(route)
        departures.add(departure)
        for day in by_day:
            seen[day] = seen.get(day, 0) + 1
    if not seen or not routes:
        return []

    # The denominator is what a full scan would have returned that day, which
    # is routes x window, not the number of departure dates ever recorded.
    per_day_window = max(1, round(len(departures) / max(1, len(seen))))
    possible = len(routes) * max(30, per_day_window)
    return [(day, min(1.0, seen[day] / possible))
            for day in sorted(seen)[-days:]]


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
    parser.add_argument("--series", default="data/date_prices.json")
    parser.add_argument("--min-coverage", type=float, default=0.75,
                        help="share of the scanned window that must return a "
                             "price, judged over consecutive days")
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
    # --- coverage -------------------------------------------------------- #
    # Freshness alone says the job ran. It does not say the job saw anything:
    # the provider answers a throttled request with HTTP 200 and no
    # itineraries, so a run can succeed, commit data, and still have missed a
    # third of the window. That slide belongs here rather than in CI, where it
    # would fail pushes that have nothing to do with it.
    #
    # Sustained, not a blip: one thin day is weather, three in a row is a
    # trend worth a human looking at.
    coverage = recent_coverage(args.series, days=STREAK_DAYS)
    if coverage:
        for day, share in coverage:
            print(f"[liveness] {day}: {share:.0%} of the window returned a price")
        thin = [d for d, share in coverage if share < args.min_coverage]
        if len(thin) >= STREAK_DAYS and len(coverage) >= STREAK_DAYS:
            print(f"[liveness] FAIL — coverage below {args.min_coverage:.0%} on "
                  f"{len(thin)} consecutive days ({', '.join(thin)}). The runs "
                  f"are succeeding; they are just not seeing the window.")
            return 1

    print("[liveness] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
