"""Price-history persistence and the "usual price" baseline.

History is a flat JSON list of observation records (one per offer we ever
recorded), stored in the repo so it survives between daily CI runs and grows
into a meaningful price distribution over time.
"""

from __future__ import annotations

import json
import os
import statistics
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from .models import Baseline, Offer

SCHEMA_VERSION = 1


# --------------------------------------------------------------------------- #
# Load / save
# --------------------------------------------------------------------------- #
def load_history(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(payload, dict):
        return list(payload.get("observations", []))
    if isinstance(payload, list):
        return payload
    return []


def save_history(path: str, records: List[dict]) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": len(records),
        "observations": records,
    }
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
    os.replace(tmp, path)


def prune_history(records: List[dict], keep_days: int, today: date) -> List[dict]:
    """Drop observations older than ``keep_days`` to keep the file bounded."""
    cutoff = today - timedelta(days=keep_days)
    kept = []
    for rec in records:
        observed = _parse_date(rec.get("observed_date"))
        if observed is None or observed >= cutoff:
            kept.append(rec)
    return kept


def append_observations(records: List[dict], offers: Iterable[Offer],
                        observed_date: str) -> List[dict]:
    for offer in offers:
        rec = offer.to_record()
        rec["observed_date"] = observed_date
        records.append(rec)
    return records


# --------------------------------------------------------------------------- #
# Baseline stats
# --------------------------------------------------------------------------- #
def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _percentile(values: List[float], pct: float) -> Optional[float]:
    """Linear-interpolation percentile (pct in 0..1). Robust for small n."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = pct * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    frac = rank - low
    return ordered[low] + (ordered[high] - ordered[low]) * frac


def compute_baseline(records: List[dict], route_key: str, trip_type: str,
                    window_days: int, as_of: date) -> Baseline:
    """The typical price for a route + trip type in the trailing window.

    ``trip_type`` ("one_way" / "round_trip") is part of the key, not a filter
    applied afterwards: a return fare is roughly twice a one-way, so mixing
    them yields a median that flags every one-way as a bargain.

    Each day is reduced to its *cheapest* observed fare before the statistics
    are taken, so ``samples`` counts days of history, not raw observations.
    That keeps the comparison like-for-like: we alert on today's cheapest fare,
    so "usual" must mean the usual cheapest fare. Averaging over every offer we
    ever stored (which includes 2nd- and 3rd-best options) would sit well above
    the daily low and make an ordinary cheapest fare look like a discount every
    single day.

    Note: pass history that does *not* include today's observations so the
    baseline represents the *usual* price to compare today's fares against.
    """
    cutoff = as_of - timedelta(days=window_days)
    cheapest_per_day: Dict[date, float] = {}
    for rec in records:
        if rec.get("origin") is None:
            continue
        rk = f"{rec.get('origin')}-{rec.get('destination')}"
        if rk != route_key:
            continue
        # Older records predate trip_type; treat them as one-way (what the
        # scanner recorded first) rather than silently pooling them.
        if (rec.get("trip_type") or "one_way") != trip_type:
            continue
        observed = _parse_date(rec.get("observed_date"))
        if observed is None or observed < cutoff or observed > as_of:
            continue
        try:
            price = float(rec["price"])
        except (KeyError, TypeError, ValueError):
            continue
        best = cheapest_per_day.get(observed)
        if best is None or price < best:
            cheapest_per_day[observed] = price

    prices: List[float] = list(cheapest_per_day.values())
    if not prices:
        return Baseline(route_key=route_key, samples=0, trip_type=trip_type)

    return Baseline(
        route_key=route_key,
        samples=len(prices),
        trip_type=trip_type,
        median=round(statistics.median(prices), 2),
        mean=round(statistics.fmean(prices), 2),
        p25=round(_percentile(prices, 0.25), 2),
        minimum=round(min(prices), 2),
        maximum=round(max(prices), 2),
    )


TRIP_TYPES = ("one_way", "round_trip")


def baselines_by_route(records: List[dict], route_keys: Iterable[str],
                       window_days: int, as_of: date
                       ) -> Dict[Tuple[str, str], Baseline]:
    """Baselines keyed by (route_key, trip_type)."""
    return {
        (rk, tt): compute_baseline(records, rk, tt, window_days, as_of)
        for rk in route_keys
        for tt in TRIP_TYPES
    }
