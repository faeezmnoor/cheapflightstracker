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
from typing import Dict, Iterable, List, Optional

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


def compute_baseline(records: List[dict], route_key: str,
                    window_days: int, as_of: date) -> Baseline:
    """The typical price for a route from observations in the trailing window.

    Note: pass history that does *not* include today's observations so the
    baseline represents the *usual* price to compare today's fares against.
    """
    cutoff = as_of - timedelta(days=window_days)
    prices: List[float] = []
    for rec in records:
        if rec.get("origin") is None:
            continue
        rk = f"{rec.get('origin')}-{rec.get('destination')}"
        if rk != route_key:
            continue
        observed = _parse_date(rec.get("observed_date"))
        if observed is None or observed < cutoff or observed > as_of:
            continue
        try:
            prices.append(float(rec["price"]))
        except (KeyError, TypeError, ValueError):
            continue

    if not prices:
        return Baseline(route_key=route_key, samples=0)

    return Baseline(
        route_key=route_key,
        samples=len(prices),
        median=round(statistics.median(prices), 2),
        mean=round(statistics.fmean(prices), 2),
        p25=round(_percentile(prices, 0.25), 2),
        minimum=round(min(prices), 2),
        maximum=round(max(prices), 2),
    )


def baselines_by_route(records: List[dict], route_keys: Iterable[str],
                       window_days: int, as_of: date) -> Dict[str, Baseline]:
    return {
        rk: compute_baseline(records, rk, window_days, as_of)
        for rk in route_keys
    }
