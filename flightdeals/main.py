"""Entry point: run a daily scan end-to-end, in one process or sharded.

Single process (small route lists, local runs):

    load config -> search every route/date -> compute baselines from prior
    history -> flag deals -> email digest -> persist today's cheapest fares.

Sharded (CI, many routes): several scan shards run in parallel, each writing
its offers to a file, then one report step merges them and does the rest.

    python run.py --shard 0 --shards 4 --output obs-0.json     # per shard
    python run.py --report obs-*.json                          # once, after
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import date, datetime, timezone
from typing import Dict, List

from .baseline import (append_observations, daily_cheapest, load_history,
                       prune_history, save_history)
from .config import Config, shard_routes
from .detector import find_deals
from .emailer import send_email
from .models import Offer, RunResult
from .providers import get_provider
from .search import plan_date_pairs, run_searches


# --------------------------------------------------------------------------- #
# Scanning
# --------------------------------------------------------------------------- #
def scan(config: Config, today: date) -> tuple[Dict[str, List[Offer]], List[str]]:
    """Search every route x date for this config's routes."""
    print(f"[scan] {today.isoformat()} | provider={config.provider} | "
          f"routes={len(config.routes)} | currency={config.currency}")
    provider = get_provider(config)
    offers_by_route, errors = run_searches(provider, config, today)
    checked = sum(len(v) for v in offers_by_route.values())
    print(f"[scan] collected {checked} offers, {len(errors)} error(s)")
    for err in errors[:8]:
        print(f"[scan]   ! {err}")
    if len(errors) > 8:
        print(f"[scan]   ! ...and {len(errors) - 8} more")
    empty = [r.label for r in config.routes if not offers_by_route.get(r.key)]
    if empty:
        print(f"[scan] routes with no offers: {', '.join(empty)}")
    return offers_by_route, errors


def write_shard(path: str, today: date, offers_by_route: Dict[str, List[Offer]],
                errors: List[str], config: Config) -> None:
    """Persist a shard's findings for the report step to pick up."""
    payload = {
        "run_date": today.isoformat(),
        "errors": errors,
        "scanned_departures": sorted({d for d, _ in plan_date_pairs(config, today)}),
        # How many fares were actually examined, before compaction — the
        # digest reports this, not the handful of survivors.
        "offers_scanned": sum(len(v) for v in offers_by_route.values()),
        # Only the cheapest per route/trip-type survives — that is all the
        # baseline uses, and it keeps the artifacts (and history) small.
        "offers": [o.to_record() for o in
                   daily_cheapest(o for v in offers_by_route.values() for o in v)],
    }
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
    print(f"[scan] wrote {len(payload['offers'])} cheapest fares -> {path}")


def read_shards(patterns: List[str]) -> tuple[Dict[str, List[Offer]], List[str],
                                              List[str], str | None, int]:
    """Merge shard files back into offers/errors/scanned dates."""
    paths: List[str] = []
    for pattern in patterns:
        paths.extend(sorted(glob.glob(pattern)))
    if not paths:
        raise SystemExit(f"[fatal] no shard files matched: {patterns}")

    offers_by_route: Dict[str, List[Offer]] = {}
    errors: List[str] = []
    scanned: set[str] = set()
    run_date = None
    scanned_count = 0
    for path in paths:
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        run_date = run_date or payload.get("run_date")
        errors.extend(payload.get("errors") or [])
        scanned.update(payload.get("scanned_departures") or [])
        scanned_count += int(payload.get("offers_scanned") or 0)
        for record in payload.get("offers") or []:
            offer = Offer.from_record(record)
            offers_by_route.setdefault(offer.route_key, []).append(offer)
        print(f"[report] loaded {len(payload.get('offers') or [])} fares "
              f"from {path}")
    return offers_by_route, errors, sorted(scanned), run_date, scanned_count


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def report(config: Config, today: date,
           offers_by_route: Dict[str, List[Offer]], errors: List[str],
           scanned: List[str], offers_checked: int) -> RunResult:
    """Compare against history, email the digest, then persist today's fares."""
    # Baselines must reflect PRIOR history, so evaluate before appending.
    history = load_history(config.history_path)
    deals, summaries = find_deals(
        offers_by_route, history, config.routes, config, today
    )
    print(f"[report] flagged {len(deals)} deal(s)")

    result = RunResult(
        run_date=today.isoformat(),
        currency=config.currency,
        deals=deals,
        summaries=summaries,
        offers_checked=offers_checked,
        errors=errors,
        scanned_departures=scanned,
    )
    send_email(result, config)

    cheapest = daily_cheapest(o for v in offers_by_route.values() for o in v)
    history = append_observations(history, cheapest, today.isoformat())
    history = prune_history(history, config.history_window_days + 30, today)
    save_history(config.history_path, history)
    print(f"[report] history now holds {len(history)} observations "
          f"-> {config.history_path}")
    return result


def run(config: Config, today: date | None = None) -> RunResult:
    """Single-process scan + report (no sharding)."""
    today = today or datetime.now(timezone.utc).date()
    offers_by_route, errors = scan(config, today)
    checked = sum(len(v) for v in offers_by_route.values())
    scanned = sorted({d for d, _ in plan_date_pairs(config, today)})
    return report(config, today, offers_by_route, errors, scanned, checked)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Daily KL->Indonesia flight-deal scan")
    parser.add_argument("--provider", help="Override PROVIDER (googleflights|mock)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the email instead of sending it")
    parser.add_argument("--date", help="Override 'today' as YYYY-MM-DD (testing)")
    parser.add_argument("--shard", type=int, help="This shard's index (0-based)")
    parser.add_argument("--shards", type=int, default=1,
                        help="Total number of scan shards")
    parser.add_argument("--output", help="Scan only; write findings here")
    parser.add_argument("--report", nargs="+", metavar="FILE",
                        help="Report only; merge these shard files")
    args = parser.parse_args(argv)

    config = Config.from_env()
    if args.provider:
        config.provider = args.provider
    if args.dry_run:
        config.dry_run = True
    today = (datetime.strptime(args.date, "%Y-%m-%d").date() if args.date
             else datetime.now(timezone.utc).date())

    try:
        if args.report:
            offers, errors, scanned, run_date, checked = read_shards(args.report)
            if run_date and not args.date:
                today = datetime.strptime(run_date, "%Y-%m-%d").date()
            report(config, today, offers, errors, scanned,
                   checked or sum(len(v) for v in offers.values()))
        elif args.output:
            if args.shard is not None:
                config.routes = shard_routes(config.routes, args.shard, args.shards)
                print(f"[scan] shard {args.shard}/{args.shards}: "
                      f"{[r.destination for r in config.routes]}")
            offers, errors = scan(config, today)
            write_shard(args.output, today, offers, errors, config)
        else:
            run(config, today)
    except Exception as exc:  # noqa: BLE001
        print(f"[fatal] {exc!r}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
