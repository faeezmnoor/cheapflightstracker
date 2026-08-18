"""The far-horizon lane: fares 45-180 days out, scanned weekly and sampled.

Separate from the daily 30-day scan on purpose, and the separation is the whole
design:

* **Sampled, not exhaustive.** Every ~15 days rather than every date. The daily
  window stays exhaustive so "cheapest in the next 30 days" remains a claim we
  can support; this lane never borrows that word.
* **Its own store and its own comparison.** A 150-day fare is never pooled with
  a 30-day one. Pooling two populations with different means is exactly the
  defect that made every one-way look half price when round-trips shared their
  baseline.
* **Weekly.** Fares this far out move slowly, and the daily request budget is
  already being throttled.

What it answers is a different question from the digest's: not "is today's fare
unusual for this route" but "is it worth waiting and flying later".
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

SCHEMA_VERSION = 1

# route|trip_type|departure_date -> {observed_date: price}
HorizonStore = Dict[str, Dict[str, float]]


@dataclass
class HorizonFind:
    """A far-out fare that beats everything in the near window."""

    route_key: str
    city: str
    price: float
    currency: str
    departure_date: str
    observed_date: str
    near_cheapest: float          # best fare in the next 30 days
    discount_vs_near: float       # 0.0-1.0
    days_ahead: int
    maps_url: str = ""
    deep_link: Optional[str] = None

    @property
    def saving(self) -> float:
        return round(self.near_cheapest - self.price, 2)


def load_horizon(path: str) -> HorizonStore:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}
    series = payload.get("series") if isinstance(payload, dict) else None
    return series if isinstance(series, dict) else {}


def save_horizon(path: str, store: HorizonStore) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"schema_version": SCHEMA_VERSION,
                   "updated_at": datetime.utcnow().isoformat(timespec="seconds"),
                   "count": len(store), "series": store},
                  fh, indent=1, sort_keys=True)


def series_key(route_key: str, trip_type: str, departure_date: str) -> str:
    return f"{route_key}|{trip_type}|{departure_date}"


def record(store: HorizonStore, offers, observed_date: str) -> HorizonStore:
    """Store the cheapest fare seen per (route, trip type, departure date)."""
    for offer in offers:
        key = series_key(offer.route_key, offer.trip_type, offer.departure_date)
        bucket = store.setdefault(key, {})
        price = float(offer.price)
        if observed_date not in bucket or price < bucket[observed_date]:
            bucket[observed_date] = price
    return store


def prune(store: HorizonStore, today: date) -> HorizonStore:
    """Drop departure dates that have already passed."""
    cutoff = today.isoformat()
    return {k: v for k, v in store.items() if k.rsplit("|", 1)[-1] >= cutoff}


def latest_by_route(store: HorizonStore, today: date,
                    max_age_days: int = 21) -> Dict[str, List[tuple]]:
    """Most recent price per (route, departure date), ignoring stale readings.

    A fare seen three weeks ago is not a fare you can book today, so anything
    older than ``max_age_days`` is dropped rather than quietly presented as
    current.
    """
    floor = (today - timedelta(days=max_age_days)).isoformat()
    out: Dict[str, List[tuple]] = {}
    for key, by_day in store.items():
        route_key, trip_type, departure = key.split("|")
        fresh = {d: p for d, p in by_day.items() if d >= floor}
        if not fresh or departure < today.isoformat():
            continue
        observed = max(fresh)
        out.setdefault(route_key, []).append(
            (fresh[observed], departure, observed, trip_type))
    return out


def find_bargains(store: HorizonStore, near_cheapest: Dict[str, float],
                  today: date, min_discount: float,
                  cities: Optional[Dict[str, str]] = None,
                  maps_urls: Optional[Dict[str, str]] = None,
                  currency: str = "MYR") -> List[HorizonFind]:
    """Far fares that beat the best the next 30 days can offer.

    ``near_cheapest`` is this run's cheapest fare per route. The comparison is
    deliberately against the near window rather than against a horizon
    baseline: the question a traveller is asking here is "would waiting be
    cheaper", and that is answered by comparing the two windows, not by asking
    whether a far fare is unusual among far fares.
    """
    finds: List[HorizonFind] = []
    for route_key, rows in latest_by_route(store, today).items():
        near = near_cheapest.get(route_key)
        if not near:
            continue
        price, departure, observed, _ = min(rows)
        if price >= near:
            continue
        discount = (near - price) / near
        if discount < min_discount:
            continue
        finds.append(HorizonFind(
            route_key=route_key,
            city=(cities or {}).get(route_key, route_key.split("-")[-1]),
            price=price, currency=currency,
            departure_date=departure, observed_date=observed,
            near_cheapest=near, discount_vs_near=round(discount, 4),
            days_ahead=(date.fromisoformat(departure) - today).days,
            maps_url=(maps_urls or {}).get(route_key, ""),
        ))
    finds.sort(key=lambda f: f.discount_vs_near, reverse=True)
    return finds
