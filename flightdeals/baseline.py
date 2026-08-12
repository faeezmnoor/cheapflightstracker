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


# --------------------------------------------------------------------------- #
# Alert state: what we have already told the user
#
# Statistics decide whether a fare is unusual; they cannot decide whether it is
# *news*. A fare that stays cheap remains unusual against months of history and
# would be re-sent every morning until the median caught up. Remembering the
# last alert per route makes repetition an explicit decision rather than a
# side effect of the maths.
# --------------------------------------------------------------------------- #
def load_alert_state(path: str) -> Dict[str, dict]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}
    alerts = payload.get("alerts") if isinstance(payload, dict) else None
    return alerts if isinstance(alerts, dict) else {}


def save_alert_state(path: str, alerts: Dict[str, dict]) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"schema_version": SCHEMA_VERSION, "alerts": alerts},
                  fh, indent=2, sort_keys=True)
    os.replace(tmp, path)


def should_repeat(previous: Optional[dict], price: float, today: date,
                  improvement: float, cooldown_days: int) -> bool:
    """Is this worth saying again?

    Only when the fare has dropped materially since the last alert, or enough
    days have passed that a reminder is useful rather than noise.
    """
    if not previous:
        return True
    last_price = previous.get("price")
    if last_price is None:
        return True
    if price <= float(last_price) * (1 - improvement):
        return True
    last_seen = _parse_date(previous.get("date"))
    if last_seen is None:
        return True
    return (today - last_seen).days >= cooldown_days


# --------------------------------------------------------------------------- #
# Per-departure-date price series
#
# The route-level history answers "is today's cheapest fare low for this
# route?". It cannot tell a genuine price drop from a cheap date simply
# scrolling into the rolling 30-day window — both look like the headline
# falling. This series tracks each departure date separately, so a fare can be
# compared against what that *same date* cost on previous days.
#
# Shape (deliberately compact — this is committed daily):
#   {"KUL-CGK|one_way|2026-09-08": {"2026-08-09": 608.0, "2026-08-10": 469.0}}
# --------------------------------------------------------------------------- #
DateSeries = Dict[str, Dict[str, float]]


def series_key(route_key: str, trip_type: str, departure_date: str) -> str:
    return f"{route_key}|{trip_type}|{departure_date}"


def load_date_series(path: str) -> DateSeries:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}
    series = payload.get("series") if isinstance(payload, dict) else None
    return series if isinstance(series, dict) else {}


def save_date_series(path: str, series: DateSeries) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "series_count": len(series),
        "series": series,
    }
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        # No indent: this file is machine-read and committed every day.
        json.dump(payload, fh, sort_keys=True, separators=(",", ":"))
    os.replace(tmp, path)


def record_date_prices(series: DateSeries, offers: Iterable[Offer],
                       observed_date: str) -> DateSeries:
    """Record today's cheapest fare for each departure date."""
    for offer in offers:
        key = series_key(offer.route_key, offer.trip_type, offer.departure_date)
        bucket = series.setdefault(key, {})
        existing = bucket.get(observed_date)
        if existing is None or offer.price < existing:
            bucket[observed_date] = round(float(offer.price), 2)
    return series


def prune_date_series(series: DateSeries, today: date,
                      keep_observations: int = 45) -> DateSeries:
    """Drop departure dates that have passed and trim stale observations.

    A departure date stops being scanned once it falls out of the window, so
    its series can never grow again — keeping it would bloat the file forever.
    """
    pruned: DateSeries = {}
    for key, observations in series.items():
        parts = key.split("|")
        if len(parts) != 3:
            continue
        departure = _parse_date(parts[2])
        if departure is None or departure < today:
            continue
        recent = dict(sorted(observations.items())[-keep_observations:])
        if recent:
            pruned[key] = recent
    return pruned


def date_baseline(series: DateSeries, route_key: str, trip_type: str,
                  departure_date: str, as_of: date
                  ) -> tuple[Optional[float], int, Optional[float], Optional[str]]:
    """What this exact departure date usually costs, before today.

    Returns (median, samples, most_recent_price, most_recent_date). Only
    observations strictly before ``as_of`` count, so today's scan cannot
    contaminate the baseline it is being judged against.
    """
    observations = series.get(series_key(route_key, trip_type, departure_date))
    if not observations:
        return None, 0, None, None
    cutoff = as_of.isoformat()
    prior = {d: p for d, p in observations.items() if d < cutoff}
    if not prior:
        return None, 0, None, None
    latest = max(prior)
    prices = list(prior.values())
    return (round(statistics.median(prices), 2), len(prices),
            prior[latest], latest)


def daily_cheapest_by_date(offers: Iterable[Offer]) -> List[Offer]:
    """Cheapest fare per (route, trip type, departure date).

    One entry per date scanned rather than one per route, so the per-date
    series can be built and the route-level cheapest still derived from it.
    """
    best: Dict[tuple, Offer] = {}
    for offer in offers:
        key = (offer.route_key, offer.trip_type, offer.departure_date)
        current = best.get(key)
        if current is None or offer.price < current.price:
            best[key] = offer
    return sorted(best.values(),
                  key=lambda o: (o.route_key, o.trip_type, o.departure_date))


def daily_cheapest(offers: Iterable[Offer]) -> List[Offer]:
    """Reduce a day's offers to the cheapest per (route, trip type).

    Exhaustive scanning produces thousands of offers a day; persisting them all
    would grow the committed history into tens of megabytes within months. The
    baseline only ever uses each day's cheapest fare, so storing just that
    loses nothing it depends on.
    """
    best: Dict[tuple, Offer] = {}
    for offer in offers:
        key = (offer.route_key, offer.trip_type)
        current = best.get(key)
        if current is None or offer.price < current.price:
            best[key] = offer
    return sorted(best.values(), key=lambda o: (o.route_key, o.trip_type))


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
