"""Decide which of today's fares are genuinely unusual, and why.

The rule, in one line: **alert on the route's own cheapest fare, only when it
is rare by its own history, by a margin worth an email.**

Three earlier designs failed on live data and are worth recording, because
each failure is a constraint on this one:

* Comparing today's cheapest against the *mean* of every stored offer flagged
  something every single day — the mean of a right-skewed distribution sits
  well above the daily low it was being compared to.
* Comparing against yesterday's price for the *same departure date* looked
  rigorous but rested on a single observation. Roughly 7% of dates swing more
  than 2x day to day, mostly from scrapes that miss the cheap itineraries, so
  a lone high reading manufactured an "85% off" alert.
* Taking the best discount across ~30 dates per route turned that noise into a
  search: with 30 chances, nearly every route found one date whose previous
  reading happened to be junk. 21 of 26 routes alerted in a single morning,
  and one alert quoted 309 while the digest showed 279 available on the same
  route.

So: one candidate per route (its cheapest fare), robust statistics rather than
means, and several independent reasons any of which can qualify — each backed
by an absolute floor so a few ringgit off a steady price is never "severe".
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from .baseline import DateSeries, date_baseline, should_repeat
from .config import Config, Route
from .models import Baseline, Deal, Offer, RouteSummary
from .stats import (PriceStats, build_daily_series, days_since_at_or_below,
                    rarity_label, summarise)


def _severity(stats: PriceStats, price: float, config: Config,
              is_new_low: bool, percentile: float, z: float) -> Optional[str]:
    """Grade a fare, or return None if it is not worth an alert.

    Every path requires a meaningful percentage discount *and* a meaningful
    cash saving. A z-score alone is not enough: a route whose fare has been
    identical for a week has a tiny scale, so trivial dips score extreme
    z-values that mean nothing to a traveller.
    """
    discount = stats.discount_vs_median(price)
    saving = stats.median - price
    if discount < config.min_discount or saving < config.min_saving:
        return None

    # "Severe" has to mean rare *and* large, and for a while it did not. The
    # first clause used to be a bare discount test, so a fare could be shouted
    # about on size alone: KL->Banjarmasin held MYR 259 against a 429 median
    # for eight consecutive days, and was labelled SEVERELY UNDERPRICED every
    # one of them while its percentile climbed 0% -> 5% -> ... -> 26%. By the
    # end, a quarter of tracked days had that price. It was the going rate.
    #
    # This is the stale-price-level failure that `deal_percentile_guard` fixed
    # on the ordinary path, and it survived here because only one of the two
    # paths was guarded. The stricter label had the looser rarity test.
    severe = (
        (discount >= config.severe_threshold
         and percentile <= config.rare_percentile)
        or (discount >= config.severe_discount_floor and is_new_low)
    )
    if severe:
        return "severe"

    # Rarity is the honest measure, so neither a z-score nor a plain discount
    # qualifies a fare unless the empirical percentile agrees it is towards the
    # cheap end. Without that guard on the discount path, a fare that steps
    # down to a new level and holds there stays "20% off" until the median
    # catches up days later — announcing an old price change as today's news.
    qualifies = (
        is_new_low
        or percentile <= config.rare_percentile
        or (discount >= config.deal_threshold
            and percentile <= config.deal_percentile_guard)
        or (z <= config.deal_z and percentile <= config.z_percentile_guard)
    )
    return "deal" if qualifies else None


def find_deals(
    offers_by_route: Dict[str, List[Offer]],
    history: List[dict],
    routes: List[Route],
    config: Config,
    today: date,
    date_series: Optional[DateSeries] = None,
    last_alerts: Optional[Dict[str, dict]] = None,
    scanned_departures: Optional[List[str]] = None,
) -> tuple[List[Deal], List[RouteSummary]]:
    """Flag unusually cheap fares and build the per-route digest.

    ``history`` and ``date_series`` must hold only observations from *before*
    today, so a baseline never includes the fare it is judging.
    """
    date_series = date_series or {}
    last_alerts = last_alerts or {}
    deals: List[Deal] = []
    summaries: List[RouteSummary] = []
    cutoff = today.isoformat()
    scanned_count = len(set(scanned_departures or []))

    for route in routes:
        offers = sorted(offers_by_route.get(route.key, []),
                        key=lambda o: (o.price, o.departure_date))
        cheapest = offers[0] if offers else None

        # "Cheapest" is only a minimum if the scan actually saw the window. When
        # the provider returns a handful of dates, the lowest of them is a
        # sample that happens to be the smallest — reliably an over-estimate,
        # since the cheap dates are the ones most often missing.
        dates_seen = len({o.departure_date for o in offers})
        thin = bool(scanned_count
                    and dates_seen < scanned_count * config.min_date_coverage)

        daily = (build_daily_series(history, route.key,
                                    cheapest.trip_type if cheapest else "one_way",
                                    cutoff) if cheapest else {})
        stats = summarise(list(daily.values())) if daily else None
        trusted = bool(stats and stats.samples >= config.min_samples)

        # ---------------- digest row ---------------------------------- #
        baseline = Baseline(
            route_key=route.key,
            samples=stats.samples if stats else 0,
            trip_type=cheapest.trip_type if cheapest else "one_way",
            median=stats.median if stats else None,
            minimum=stats.minimum if stats else None,
            maximum=stats.maximum if stats else None,
        )
        summary_discount = None
        if cheapest and trusted and stats and stats.median:
            summary_discount = round(stats.discount_vs_median(cheapest.price), 4)
        summaries.append(RouteSummary(
            route_key=route.key,
            city=route.city,
            cheapest=cheapest,
            baseline=baseline,
            discount_pct=summary_discount,
            baseline_trusted=trusted,
            maps_url=route.maps_url,
            dates_seen=dates_seen,
            dates_scanned=scanned_count,
        ))

        # ---------------- alert --------------------------------------- #
        # Only ever the route's cheapest fare. Scoring every date and keeping
        # the best discount is what turned per-date noise into daily spam, and
        # it produced alerts for fares worse than the one shown in the digest.
        if not (cheapest and trusted and stats and stats.median):
            continue

        # A thin scrape cannot produce an alert in either direction. It inflates
        # today's "cheapest", so it will not usually look like a deal — but the
        # same gap makes any discount it *does* show unverifiable, and quietly
        # records an over-estimate into the baseline that judges tomorrow.
        if thin:
            continue

        z = stats.z_score(cheapest.price)
        percentile = stats.percentile_of(cheapest.price)
        new_low = stats.is_new_low(cheapest.price)
        severity = _severity(stats, cheapest.price, config, new_low, percentile, z)
        if severity is None:
            continue

        # Unusual is not the same as newsworthy: a fare that stays cheap stays
        # unusual, and would be re-sent every morning until the median caught
        # up with it.
        if not should_repeat(last_alerts.get(route.key), cheapest.price, today,
                             config.repeat_improvement,
                             config.repeat_cooldown_days):
            continue

        since = days_since_at_or_below(daily, cheapest.price)

        # The per-date series only ever *annotates* an alert now. It is far too
        # noisy to originate one, but when a date has several prior sightings
        # it can say what this same date used to cost.
        prev_price = prev_date = None
        basis = "route"
        median_for_date, date_samples, last_price, last_date = date_baseline(
            date_series, cheapest.route_key, cheapest.trip_type,
            cheapest.departure_date, today)
        if date_samples >= config.min_date_samples and median_for_date:
            if cheapest.price < median_for_date:
                basis = "date_drop"
                prev_price, prev_date = last_price, last_date

        deals.append(Deal(
            offer=cheapest,
            baseline=baseline,
            discount_pct=round(stats.discount_vs_median(cheapest.price), 4),
            saving=round(stats.median - cheapest.price, 2),
            severity=severity,
            city=route.city,
            maps_url=route.maps_url,
            basis=basis,
            previous_price=prev_price,
            previous_date=prev_date,
            basis_samples=stats.samples,
            z_score=round(z, 2),
            percentile=round(percentile, 4),
            is_new_low=new_low,
            days_since_cheaper=since,
            rarity=rarity_label(stats, cheapest.price, since),
        ))

    # Rarest first: a new low outranks everything, then how far below the
    # usual price it sits.
    deals.sort(key=lambda d: (d.is_new_low, d.discount_pct), reverse=True)
    return deals, summaries
