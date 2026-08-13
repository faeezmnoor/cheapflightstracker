#!/usr/bin/env python3
"""Re-run a past day's decisions from recorded history and audit the result.

This is the regression test that fixtures cannot be: it takes the real price
history in ``data/``, replays a day the service actually ran, and puts the
resulting digest through the independent auditor. A change to the detector,
the statistics or the emailer that would have produced a wrong email *on real
data* fails here, in CI, before it can reach an inbox.

    python scripts/replay_audit.py                 # most recent recorded day
    python scripts/replay_audit.py --date 2026-08-12
    python scripts/replay_audit.py --all --strict  # every day on record

Alert-repeat suppression is deliberately switched off during a replay. The
question is "would this alert have been correct", not "was it new" — and
suppression would hide most candidates from the audit.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flightdeals.artifact import digest_payload
from flightdeals.config import Config
from flightdeals.detector import find_deals
from flightdeals.emailer import build_html
from flightdeals.models import Offer, RunResult
from flightdeals.search import plan_date_pairs
from qa.checks import audit
from qa.findings import BLOCK, WARN


def load_observations(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    return raw.get("observations", []) if isinstance(raw, dict) else (raw or [])


def replay(observations: List[dict], run_date: str, config: Config,
           series: dict) -> tuple:
    prior = [o for o in observations if (o.get("observed_date") or "") < run_date]
    today = [Offer.from_record(o) for o in observations
             if o.get("observed_date") == run_date]
    by_route: dict = {}
    for offer in today:
        by_route.setdefault(offer.route_key, []).append(offer)

    as_date = date.fromisoformat(run_date)
    deals, summaries = find_deals(by_route, prior, config.routes, config,
                                  as_date, series, {})
    result = RunResult(
        run_date, config.currency, deals, summaries, len(today), [],
        scanned_departures=sorted({d for d, _ in plan_date_pairs(config, as_date)}),
    )
    return result, prior


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="which recorded day to replay")
    parser.add_argument("--all", action="store_true",
                        help="replay every day that has enough prior history")
    parser.add_argument("--strict", action="store_true",
                        help="treat warnings as failures too")
    parser.add_argument("--history", default="data/price_history.json")
    parser.add_argument("--series", default="data/date_prices.json")
    args = parser.parse_args(argv)

    observations = load_observations(args.history)
    if not observations:
        print("[replay] no recorded history — nothing to replay (not a failure)")
        return 0

    series = {}
    if os.path.exists(args.series):
        with open(args.series, "r", encoding="utf-8") as fh:
            series = json.load(fh)

    config = Config.from_env()
    days = sorted({o["observed_date"] for o in observations
                   if o.get("observed_date")})
    if args.date:
        targets = [args.date]
    elif args.all:
        # The earliest day has no prior history to judge against, so it can
        # only ever produce "building baseline" rows.
        targets = days[1:]
    else:
        targets = days[-1:]

    worst = 0
    for run_date in targets:
        result, prior = replay(observations, run_date, config, series)
        payload = digest_payload(result, config)
        report = audit(payload, prior, build_html(result))
        severities = {f.severity for f in report.findings}
        status = ("BLOCK" if BLOCK in severities else
                  "WARN" if WARN in severities else "ok")
        print(f"[replay] {run_date}: {len(result.summaries)} routes, "
              f"{len(result.deals)} alert(s) -> {status}")
        if report.findings:
            print("\n".join("    " + f.render() for f in report.findings))
        if report.blocking:
            worst = max(worst, 2)
        elif report.findings and args.strict:
            worst = max(worst, 1)

    if worst == 0:
        print(f"[replay] {len(targets)} day(s) replayed clean")
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
