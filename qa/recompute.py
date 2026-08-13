"""A second, independent derivation of the numbers the digest claims.

Written from the *specification* rather than from ``flightdeals.stats``, and
kept import-free of that package on purpose. Two implementations that agree
are evidence; one implementation checking itself is not.

The specification, in full:

* A route's baseline is built from its **daily cheapest** fare — one number per
  observed day, not every offer seen that day. Pooling raw offers biases the
  baseline upwards, because most offers on any day are worse than the best one.
* One-way and round-trip fares are **separate populations**. A return ticket
  costs roughly double, so a shared baseline sits between the two and makes
  every one-way look about half price.
* Only observations from **strictly before** the run date count. A fare must
  never help set the baseline it is being judged against.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence

# Same convention as the code under test: scale the median absolute deviation
# so it is comparable to a standard deviation for normally distributed data.
MAD_TO_SIGMA = 1.4826

# A route whose fare never moves has MAD 0, which would make every trivial dip
# an infinite z-score. Floor the scale at a fraction of the median.
MIN_SCALE_FRACTION = 0.03


def median(values: Sequence[float]) -> Optional[float]:
    """Plain median. Written out rather than imported so that a change in the
    code under test cannot silently change the checker too."""
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return None
    mid = n // 2
    if n % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def mad(values: Sequence[float]) -> Optional[float]:
    """Median absolute deviation — the outlier-proof spread."""
    centre = median(values)
    if centre is None:
        return None
    return median([abs(v - centre) for v in values])


def scale(values: Sequence[float]) -> Optional[float]:
    """MAD rescaled to sigma-equivalent units, floored so it is never zero."""
    centre = median(values)
    spread = mad(values)
    if centre is None or spread is None:
        return None
    return max(spread * MAD_TO_SIGMA, centre * MIN_SCALE_FRACTION)


def modified_z(values: Sequence[float], price: float) -> Optional[float]:
    centre = median(values)
    sigma = scale(values)
    if centre is None or not sigma:
        return None
    return (price - centre) / sigma


def percentile_of(values: Sequence[float], price: float) -> Optional[float]:
    """Fraction of tracked days that were this cheap or cheaper.

    No distributional assumption — just counting, which is why it is the
    measure the auditor trusts most.
    """
    if not values:
        return None
    return sum(1 for v in values if v <= price) / float(len(values))


def route_key_of(observation: dict) -> str:
    return f"{observation.get('origin')}-{observation.get('destination')}"


def daily_cheapest(
    observations: Iterable[dict],
    route_key: str,
    trip_type: str,
    before_date: Optional[str] = None,
) -> Dict[str, float]:
    """Collapse history to one price per observed day for this route+trip type.

    ``before_date`` is exclusive: pass the run date to exclude fares observed
    today, which must not contribute to the baseline that judges them.
    """
    by_day: Dict[str, float] = {}
    for obs in observations:
        if route_key_of(obs) != route_key:
            continue
        if trip_type and obs.get("trip_type") != trip_type:
            continue
        day = obs.get("observed_date")
        if not day:
            continue
        if before_date is not None and day >= before_date:
            continue
        try:
            price = float(obs["price"])
        except (KeyError, TypeError, ValueError):
            continue
        if price <= 0:
            continue
        if day not in by_day or price < by_day[day]:
            by_day[day] = price
    return by_day


def baseline_for(
    observations: Iterable[dict],
    route_key: str,
    trip_type: str,
    before_date: Optional[str] = None,
) -> dict:
    """Everything the auditor needs to second-guess one route's alert."""
    series = daily_cheapest(observations, route_key, trip_type, before_date)
    prices: List[float] = list(series.values())
    return {
        "series": series,
        "samples": len(prices),
        "median": median(prices),
        "minimum": min(prices) if prices else None,
        "maximum": max(prices) if prices else None,
    }


def discount_vs(median_price: Optional[float], price: float) -> Optional[float]:
    if not median_price:
        return None
    return (median_price - price) / median_price
