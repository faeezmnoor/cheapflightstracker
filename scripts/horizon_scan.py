#!/usr/bin/env python3
"""Scan two contiguous 30-day blocks well beyond the daily window.

Run weekly, separately from the daily digest — fares this far out move slowly,
and the daily scan is already competing for a throttled request budget.

    python scripts/horizon_scan.py                      # every route
    python scripts/horizon_scan.py --shard 0 --shards 4
    python scripts/horizon_scan.py --provider mock --dry-run

**Exhaustive within each block**, exactly like the near window. An earlier
version sampled every 15th day and could not support its own conclusion: on our
own data, taking 10 of 30 dates misses the true cheapest fare 41% of the time
and reads a mean 13.9% high — against a 15% discount threshold, so the bias and
the signal were the same size. Sparse probes also land on peak dates by luck.

Both blocks are compared min-to-min against the near window, which is only fair
because both are measured the same way.
"""Scan the far horizon (45-180 days out) and record what it costs.

Run weekly, separately from the daily digest. Fares this far out move slowly,
and the daily scan is already competing for a throttled request budget — a
second lane sharing that budget would degrade the thing people actually read.

    python scripts/horizon_scan.py                     # every route
    python scripts/horizon_scan.py --shard 0 --shards 2
    python scripts/horizon_scan.py --provider mock --dry-run

Unlike the daily scan this is **sampled, not exhaustive** — every ~15 days
rather than every date. That is a deliberate difference in kind, and why its
results are never called "cheapest": the near window earns that word by
covering every date in it, and this lane does not.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time
from datetime import date, datetime, timedelta
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flightdeals.config import Config, shard_routes
from flightdeals.horizon import (block_dates, load_horizon, prune, record,
                                save_horizon)
from flightdeals.models import Offer
from flightdeals.providers import get_provider
from flightdeals.providers.base import ProviderError


def scan_horizon(config: Config, today: date) -> tuple[List[Offer], List[str]]:
    provider = get_provider(config)
    offline = getattr(provider, "offline", False)
    dates = [d for block in block_dates(config.horizon_block_starts,
                                        config.horizon_block_days, today)
             for d in block]
    print(f"[horizon] {today.isoformat()} | {len(config.routes)} route(s) x "
          f"{len(dates)} date(s) = {len(config.routes) * len(dates)} searches")

    found: List[Offer] = []
    errors: List[str] = []
    for route in config.routes:
        for departure in dates:
            try:
                offers = provider.search(route.origin, route.destination,
                                         departure, None)
                # Only the cheapest per date is kept: the store answers "what
                # does this date cost", and the rest is noise we would have to
                # prune later anyway.
                if offers:
                    found.append(min(offers, key=lambda o: o.price))
            except ProviderError as exc:
                errors.append(f"{route.key} {departure}: {exc}")
            except Exception as exc:                      # noqa: BLE001
                errors.append(f"{route.key} {departure}: {exc!r}")
            if not offline and config.request_pause_seconds > 0:
                base = config.request_pause_seconds
                time.sleep(base + random.uniform(0, base * 0.6))

    seen_dates = len({o.departure_date for o in found})
    print(f"[horizon] {len(found)} fare(s) across {seen_dates}/{len(dates)} "
          f"date(s), {len(errors)} error(s)")
    for err in errors[:5]:
        print(f"[horizon]   ! {err}")
    return found, errors


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", help="Override PROVIDER")
    parser.add_argument("--dry-run", action="store_true",
                        help="scan but do not write the store")
    parser.add_argument("--date", help="Override 'today' as YYYY-MM-DD")
    parser.add_argument("--shard", type=int)
    parser.add_argument("--shards", type=int, default=1)
    args = parser.parse_args(argv)

    config = Config.from_env()
    if args.provider:
        config.provider = args.provider
    today = (datetime.strptime(args.date, "%Y-%m-%d").date() if args.date
             else datetime.utcnow().date())
    if args.shard is not None:
        config.routes = shard_routes(config.routes, args.shard, args.shards)
        print(f"[horizon] shard {args.shard}/{args.shards}: "
              f"{[r.destination for r in config.routes]}")

    offers, _ = scan_horizon(config, today)

    if args.dry_run:
        print("[horizon] dry run — store left untouched")
        for o in sorted(offers, key=lambda o: o.price)[:10]:
            print(f"  {o.route_key} {o.departure_date} {o.currency} {o.price:,.0f}")
        return 0

    store = load_horizon(config.horizon_path)
    store = record(store, offers, today.isoformat())
    store = prune(store, today)
    save_horizon(config.horizon_path, store)
    print(f"[horizon] {len(store)} series -> {config.horizon_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
