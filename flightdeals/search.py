"""Plan and execute the day's searches across all routes and dates."""

from __future__ import annotations

import random
import time
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from .config import Config, Route
from .models import Offer
from .providers.base import FlightProvider, ProviderError


def plan_date_pairs(config: Config, today: date) -> List[Tuple[str, Optional[str]]]:
    """Build (departure_date, return_date|None) pairs to search per route.

    Always includes one-way probes for each departure offset. When round-trip
    is enabled, also adds return dates for each stay length, clamped so the
    trip never exceeds ``max_trip_days``.
    """
    pairs: List[Tuple[str, Optional[str]]] = []
    seen = set()

    for offset in config.departure_offsets:
        dep = today + timedelta(days=offset)
        dep_str = dep.isoformat()

        key = (dep_str, None)
        if key not in seen:
            seen.add(key)
            pairs.append(key)

        if config.round_trip:
            for stay in config.stay_lengths:
                if stay <= 0 or stay > config.max_trip_days:
                    continue
                ret_str = (dep + timedelta(days=stay)).isoformat()
                key = (dep_str, ret_str)
                if key not in seen:
                    seen.add(key)
                    pairs.append(key)
    return pairs


def run_searches(
    provider: FlightProvider,
    config: Config,
    today: date,
) -> Tuple[Dict[str, List[Offer]], List[str]]:
    """Search every route x date pair; return offers grouped by route key."""
    date_pairs = plan_date_pairs(config, today)
    offers_by_route: Dict[str, List[Offer]] = {r.key: [] for r in config.routes}
    errors: List[str] = []

    for route in config.routes:
        for dep, ret in date_pairs:
            try:
                found = provider.search(route.origin, route.destination, dep, ret)
                offers_by_route[route.key].extend(found)
            except ProviderError as exc:
                errors.append(f"{route.key} {dep}->{ret or 'oneway'}: {exc}")
            except Exception as exc:  # noqa: BLE001 - never let one route kill the run
                errors.append(f"{route.key} {dep}->{ret or 'oneway'}: {exc!r}")
            # Jittered spacing: an exactly-periodic request pattern is an easy
            # bot signature, and bursts get throttled.
            if config.request_pause_seconds > 0:
                base = config.request_pause_seconds
                time.sleep(base + random.uniform(0, base * 0.6))

    return offers_by_route, errors
