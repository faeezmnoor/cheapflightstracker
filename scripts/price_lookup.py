#!/usr/bin/env python3
"""What do we know about a route's prices?

Everything the service records is committed JSON in ``data/``, which is
queryable but not readable — answering "what is the cheapest Yogyakarta fare we
have found" meant writing a script each time. This is that script, once.

    python scripts/price_lookup.py YIA           # by IATA code
    python scripts/price_lookup.py yogyakarta    # or by name
    python scripts/price_lookup.py --all         # every route, cheapest first

Reads the same stores the digest does, and writes nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flightdeals.baseline import load_date_series
from flightdeals.config import Config
from flightdeals.horizon import load_horizon


def observations(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    return raw.get("observations", []) if isinstance(raw, dict) else (raw or [])


def daily_cheapest(rows: List[dict]) -> Dict[str, tuple]:
    """One entry per observed day: (price, departure_date, airline)."""
    out: Dict[str, tuple] = {}
    for o in rows:
        day = o.get("observed_date")
        if not day:
            continue
        if day not in out or o["price"] < out[day][0]:
            out[day] = (o["price"], o.get("departure_date"), o.get("airline"))
    return out


def resolve(query: str, config: Config) -> Optional[object]:
    q = query.strip().lower()
    for route in config.routes:
        if q == route.destination.lower() or q in route.city.lower():
            return route
    return None


def describe(route, config: Config, money: str) -> None:
    rows = [o for o in observations(config.history_path)
            if o.get("destination") == route.destination]
    daily = daily_cheapest(rows)
    if not daily:
        print(f"  no prices recorded yet for {route.city}")
        return

    prices = sorted(p for p, _, _ in daily.values())
    best_day = min(daily, key=lambda d: daily[d][0])
    price, departure, airline = daily[best_day]
    latest_day = max(daily)

    print(f"\nKL → {route.city}  ({route.destination})")
    print(f"  cheapest ever   {money} {price:>7,.0f}   departing {departure}"
          f"   seen {best_day}"
          + (f"   {airline}" if airline else ""))
    print(f"  usual (median)  {money} {statistics.median(prices):>7,.0f}"
          f"   over {len(prices)} tracked days")
    print(f"  range           {money} {prices[0]:>7,.0f} – {prices[-1]:,.0f}")
    cur, cur_dep, _ = daily[latest_day]
    print(f"  most recent     {money} {cur:>7,.0f}   departing {cur_dep}"
          f"   seen {latest_day}")

    # How many departure dates that most recent figure was drawn from — the
    # difference between a minimum and the smallest of a few samples.
    series = load_date_series(config.date_history_path)
    seen = sum(1 for key, by_day in series.items()
               if key.split("|")[0] == route.key and latest_day in by_day)
    if seen:
        print(f"  ...from {seen} of {config.departure_window_days} departure "
              f"dates scanned that day")

    far = load_horizon(config.horizon_path)
    far_prices = [(p, key.split("|")[-1])
                  for key, by_day in far.items()
                  if key.split("|")[0] == route.key
                  for p in [min(by_day.values())]]
    if far_prices:
        cheapest_far, far_dep = min(far_prices)
        print(f"  further out     {money} {cheapest_far:>7,.0f}   departing "
              f"{far_dep}   (3-5 months ahead)")
    else:
        print("  further out     no horizon scan recorded yet")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("route", nargs="?", help="IATA code or city name")
    parser.add_argument("--all", action="store_true",
                        help="every route, cheapest-ever first")
    args = parser.parse_args(argv)

    config = Config.from_env()
    money = config.currency

    if args.all:
        rows = []
        for route in config.routes:
            daily = daily_cheapest(
                [o for o in observations(config.history_path)
                 if o.get("destination") == route.destination])
            if daily:
                best = min(daily.values())
                rows.append((best[0], route.city, route.destination, best[1]))
        print(f"\ncheapest fare ever recorded, per route ({money})\n")
        for price, city, code, departure in sorted(rows):
            print(f"  {price:>7,.0f}   KL → {city:<24} ({code})  "
                  f"departing {departure}")
        return 0

    if not args.route:
        parser.error("give a route (IATA code or city name), or --all")
    route = resolve(args.route, config)
    if not route:
        print(f"no tracked route matches {args.route!r}. Try --all.")
        return 1
    describe(route, config, money)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
