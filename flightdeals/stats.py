"""Robust statistics for deciding when a fare is genuinely unusual.

Why not mean and standard deviation
-----------------------------------
Airfare distributions are right-skewed with a hard floor (the carrier's base
fare) and a long tail of flexible, multi-stop and business fares. Worse, a
scrape occasionally misses the cheap itineraries entirely and records a fare
several times the norm — we have observed KL->Batam recorded at 2,110 on a
route that normally bottoms out at 279. A single reading like that inflates
the standard deviation enough to hide every genuine dip afterwards, and
inflates the mean enough to make ordinary fares look like bargains.

Median and MAD (median absolute deviation) ignore those outliers by
construction: an extreme value moves the median by at most one rank position
and cannot move the MAD at all unless it is near the centre.

The three questions worth asking
--------------------------------
1. **Is it rare?**  Where does this price sit in the distribution of prices we
   have actually seen? A price in the bottom few percent is rare by
   definition, with no distributional assumptions at all.
2. **Is it anomalous?**  How many robust deviations below the typical price is
   it? This is the modified z-score, and it scales across routes: -3 means the
   same thing on a 200 fare and a 2,000 fare.
3. **Is it a new low?**  Cheaper than anything we have on record, and how long
   since it was last this cheap. This is the most interpretable signal of all
   and is naturally noise-resistant: scan artifacts push prices *up*, so they
   cannot manufacture a new low.

None of these is sufficient alone — see :mod:`flightdeals.detector` for how
they are combined with absolute floors.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

# 1.4826 rescales MAD so that, for normally distributed data, it estimates the
# same quantity as the standard deviation — which is what makes the resulting
# z-scores comparable to the familiar -2/-3 thresholds.
MAD_TO_SIGMA = 1.4826

# Prices for a route can sit at exactly the same value for days (a carrier's
# standing base fare), which drives MAD to zero and would make any cheaper
# price infinitely anomalous. Flooring the scale at a fraction of the median
# keeps the z-score finite and stops a few ringgit below a very steady price
# from reading as a once-in-a-year event.
MIN_SCALE_FRACTION = 0.03


@dataclass
class PriceStats:
    """Robust summary of a route's historical daily-cheapest fares."""

    samples: int                 # days of history behind this
    median: float
    mad: float                   # raw median absolute deviation
    scale: float                 # robust sigma estimate, floored
    minimum: float
    maximum: float
    values: Sequence[float] = ()

    # -- question 2: how anomalous ------------------------------------- #
    def z_score(self, price: float) -> float:
        """Modified z-score. Negative means cheaper than usual."""
        if self.scale <= 0:
            return 0.0
        return (price - self.median) / self.scale

    # -- question 1: how rare ------------------------------------------- #
    def percentile_of(self, price: float) -> float:
        """Fraction of observed days that were at or below ``price`` (0-1).

        0.0 means nothing on record was ever this cheap.
        """
        if not self.values:
            return 1.0
        at_or_below = sum(1 for v in self.values if v <= price)
        return at_or_below / len(self.values)

    # -- question 3: is it a new low ------------------------------------ #
    def is_new_low(self, price: float) -> bool:
        return bool(self.values) and price < self.minimum

    def discount_vs_median(self, price: float) -> float:
        if not self.median:
            return 0.0
        return (self.median - price) / self.median


def summarise(values: Sequence[float]) -> Optional[PriceStats]:
    """Build robust stats from a route's daily-cheapest fares."""
    clean = [float(v) for v in values if v is not None and float(v) > 0]
    if not clean:
        return None
    median = statistics.median(clean)
    mad = statistics.median([abs(v - median) for v in clean])
    scale = max(mad * MAD_TO_SIGMA, median * MIN_SCALE_FRACTION)
    return PriceStats(
        samples=len(clean),
        median=round(median, 2),
        mad=round(mad, 2),
        scale=round(scale, 4),
        minimum=min(clean),
        maximum=max(clean),
        values=tuple(clean),
    )


def days_since_at_or_below(history: Dict[str, float], price: float) -> Optional[int]:
    """How many observation days since the fare was last this cheap.

    ``history`` maps observation date (ISO) to that day's cheapest fare, and
    must exclude today. Returns None when it has never been this cheap — the
    caller reports that as a new low rather than a number.
    """
    if not history:
        return None
    ordered = sorted(history.items(), reverse=True)      # newest first
    for offset, (_, value) in enumerate(ordered, start=1):
        if value <= price:
            return offset
    return None


def rarity_label(stats: PriceStats, price: float,
                 days_since: Optional[int]) -> str:
    """Short human phrase for how unusual this price is."""
    if stats.is_new_low(price):
        return f"cheapest in {stats.samples} days of tracking"
    if days_since is not None and days_since >= 2:
        return f"cheapest in {days_since} days"
    pct = stats.percentile_of(price)
    if pct <= 0.10:
        return f"in the cheapest {max(round(pct * 100), 1)}% of prices seen"
    return f"below the usual {stats.median:,.0f}"


def build_daily_series(records: List[dict], route_key: str, trip_type: str,
                       before: str) -> Dict[str, float]:
    """Cheapest fare per observation day for one route, excluding ``before``.

    History files mix granularity — early runs stored every offer, later ones
    only the daily cheapest — so reduce to one value per day either way.
    """
    per_day: Dict[str, float] = {}
    for rec in records:
        if rec.get("origin") is None:
            continue
        if f"{rec.get('origin')}-{rec.get('destination')}" != route_key:
            continue
        if (rec.get("trip_type") or "one_way") != trip_type:
            continue
        day = rec.get("observed_date")
        if not day or day >= before:
            continue
        try:
            price = float(rec["price"])
        except (KeyError, TypeError, ValueError):
            continue
        if price <= 0:
            continue
        if day not in per_day or price < per_day[day]:
            per_day[day] = price
    return per_day
