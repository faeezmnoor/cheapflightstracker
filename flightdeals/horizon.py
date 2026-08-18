"""The far-horizon lane: two contiguous 30-day blocks, scanned exhaustively.

Separate from the daily scan on purpose, and the separation is the design:

* **Exhaustive within each block, like the near window.** The first version
  sampled every 15th day and could not support its own conclusion — on our own
  data, 10 of 30 dates misses the true cheapest fare 41% of the time and reads
  a mean 13.9% high, against a 15% discount threshold. Sparse probes also land
  on peak dates by luck; 3 of the original 10 fell in Christmas/New Year or the
  Chinese New Year window, which is expensive for calendar reasons that have
  nothing to do with booking early.
* **Compared only when both windows are comparably covered.** Coverage drives
  the bias directly, so a well-covered near window versus a thin far block
  would manufacture a difference out of measurement.
* **Its own store, never pooled with route baselines.** A 150-day fare and a
  20-day fare are different populations; merging them repeats the failure that
  made every one-way look half price when returns shared a baseline.

One thing this lane genuinely cannot separate: **season from lead time.** A
block 5 months out is a different time of year, so "February is cheaper than
September" is supportable while "book earlier and save" is not. The wording
follows the weaker claim deliberately. Keeping the data does eventually settle
it — the same calendar dates age into the near window, and comparing a date
against itself at two lead times isolates the curve from the season.
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
    """A far block that is cheaper than everything in the next 30 days."""

    route_key: str
    city: str
    price: float
    currency: str
    departure_date: str
    observed_date: str
    near_cheapest: float          # best fare in the next 30 days
    discount_vs_near: float       # 0.0-1.0
    days_ahead: int
    block_label: str = ""         # e.g. "17 Nov - 16 Dec"
    far_seen: int = 0             # dates the far block actually returned
    far_total: int = 0
    near_seen: int = 0            # ...and the near window, for comparison
    near_total: int = 0
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


def block_dates(starts: List[int], length: int, today: date) -> List[List[str]]:
    """The contiguous departure dates each block covers, exhaustively."""
    return [[(today + timedelta(days=start + n)).isoformat()
             for n in range(length)]
            for start in sorted(starts)]


def _label(dates: List[str]) -> str:
    def short(value: str) -> str:
        d = date.fromisoformat(value)
        return f"{d.day} {d.strftime('%b')}"
    return f"{short(dates[0])} \u2013 {short(dates[-1])}"


def find_bargains(store: HorizonStore, near: Dict[str, tuple], today: date,
                  block_starts: List[int], block_days: int,
                  min_discount: float, min_coverage: float,
                  cities: Optional[Dict[str, str]] = None,
                  maps_urls: Optional[Dict[str, str]] = None,
                  currency: str = "MYR",
                  max_age_days: int = 21) -> List[HorizonFind]:
    """Blocks that are cheaper than everything the next 30 days can offer.

    ``near`` maps route -> (cheapest_price, dates_seen, dates_scanned) for this
    run. Both sides carry their coverage because the comparison is only
    meaningful when both were measured the same way: the minimum of a
    half-covered window reads about 12% high, which is most of the discount
    threshold, so a thin far block compared against a full near window would
    invent a difference out of measurement rather than find one in the market.

    The claim this supports is "flying in this block is cheaper than flying in
    the next 30 days" — a season-and-lead-time effect together. It is
    deliberately *not* "book earlier and save": the two cannot be separated
    from a single comparison.
    """
    floor = (today - timedelta(days=max_age_days)).isoformat()

    # Most recent fresh price per (route, departure date).
    latest: Dict[str, Dict[str, tuple]] = {}
    for key, by_day in store.items():
        route_key, _, departure = key.split("|")
        fresh = {d: p for d, p in by_day.items() if d >= floor}
        if not fresh or departure < today.isoformat():
            continue
        observed = max(fresh)
        latest.setdefault(route_key, {})[departure] = (fresh[observed], observed)

    finds: List[HorizonFind] = []
    for block in block_dates(block_starts, block_days, today):
        wanted = set(block)
        for route_key, prices in latest.items():
            near_row = near.get(route_key)
            if not near_row:
                continue
            near_price, near_seen, near_total = near_row
            if not near_price or not near_total:
                continue
            if near_seen / near_total < min_coverage:
                continue          # our own near window is too thin to compare

            got = {d: v for d, v in prices.items() if d in wanted}
            if len(got) / len(block) < min_coverage:
                continue          # ...and so is the block

            departure, (price, observed) = min(got.items(), key=lambda kv: kv[1][0])
            if price >= near_price:
                continue
            discount = (near_price - price) / near_price
            if discount < min_discount:
                continue

            finds.append(HorizonFind(
                route_key=route_key,
                city=(cities or {}).get(route_key, route_key.split("-")[-1]),
                price=price, currency=currency,
                departure_date=departure, observed_date=observed,
                near_cheapest=near_price, discount_vs_near=round(discount, 4),
                days_ahead=(date.fromisoformat(departure) - today).days,
                block_label=_label(block),
                far_seen=len(got), far_total=len(block),
                near_seen=near_seen, near_total=near_total,
                maps_url=(maps_urls or {}).get(route_key, ""),
            ))

    # Best saving first; a route appearing in both blocks keeps only its best.
    finds.sort(key=lambda f: f.discount_vs_near, reverse=True)
    seen_routes = set()
    unique = []
    for f in finds:
        if f.route_key in seen_routes:
            continue
        seen_routes.add(f.route_key)
        unique.append(f)
    return unique
