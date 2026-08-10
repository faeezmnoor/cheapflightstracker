"""Turn raw offers + history into deals and a per-route digest."""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from .baseline import DateSeries, baselines_by_route, date_baseline
from .config import Config, Route
from .models import Baseline, Deal, Offer, RouteSummary


def _classify(discount_pct: float, config: Config) -> Optional[str]:
    if discount_pct >= config.severe_threshold:
        return "severe"
    if discount_pct >= config.deal_threshold:
        return "deal"
    return None


def find_deals(
    offers_by_route: Dict[str, List[Offer]],
    history: List[dict],
    routes: List[Route],
    config: Config,
    today: date,
    date_series: Optional[DateSeries] = None,
) -> tuple[List[Deal], List[RouteSummary]]:
    """Compare today's offers to the baselines built from prior history.

    Two independent comparisons, in order of trustworthiness:

    1. **Per departure date.** Today's fare for 8 Sep against what 8 Sep cost
       on previous days. Like-for-like, so it cannot be fooled by the rolling
       window sliding a cheap date into view.
    2. **Per route.** Today's cheapest against the route's usual cheapest. Used
       only when a date is too new to have its own history — it answers "this
       is a cheap date", not "this fare fell".

    ``history`` and ``date_series`` must be the *prior* records (before today's
    observations are appended), so a baseline never includes what it is judging.
    """
    date_series = date_series or {}
    route_meta = {r.key: r for r in routes}
    baselines = baselines_by_route(
        history, route_meta.keys(), config.history_window_days, today
    )

    deals: List[Deal] = []
    summaries: List[RouteSummary] = []

    def _route_baseline(offer: Offer) -> Baseline:
        key = (offer.route_key, offer.trip_type)
        return baselines.get(key, Baseline(offer.route_key, 0, offer.trip_type))

    def _trusted(baseline: Baseline) -> bool:
        # Same bar for the digest and for alerts, so thin history can never
        # imply a discount.
        return bool(baseline.is_reliable and baseline.median
                    and baseline.samples >= config.min_samples)

    for route in routes:
        offers = sorted(offers_by_route.get(route.key, []),
                        key=lambda o: (o.price, o.departure_date))

        # ---------------- digest row: today's headline fare ---------------- #
        cheapest = offers[0] if offers else None
        summary_baseline = (_route_baseline(cheapest) if cheapest
                            else Baseline(route.key, 0))
        summary_discount = None
        if cheapest and _trusted(summary_baseline) and summary_baseline.median:
            summary_discount = round(
                (summary_baseline.median - cheapest.price)
                / summary_baseline.median, 4
            )
        summaries.append(RouteSummary(
            route_key=route.key,
            city=route.city,
            cheapest=cheapest,
            baseline=summary_baseline,
            discount_pct=summary_discount,
            baseline_trusted=_trusted(summary_baseline),
        ))

        # ---------------- alerts ------------------------------------------ #
        drops: List[Deal] = []       # this date got cheaper than it was
        cheap_dates: List[Deal] = []  # date has no history; judged on route
        for offer in offers:
            median, samples, prev_price, prev_date = date_baseline(
                date_series, offer.route_key, offer.trip_type,
                offer.departure_date, today
            )
            if median and samples >= config.min_date_samples:
                discount = (median - offer.price) / median
                severity = _classify(discount, config)
                if severity:
                    drops.append(Deal(
                        offer=offer,
                        baseline=Baseline(offer.route_key, samples,
                                          offer.trip_type, median=median),
                        discount_pct=round(discount, 4),
                        saving=round(median - offer.price, 2),
                        severity=severity,
                        city=route.city,
                        basis="date_drop",
                        previous_price=prev_price,
                        previous_date=prev_date,
                        basis_samples=samples,
                    ))
                continue

            # No history for this date yet — fall back to the route baseline.
            route_base = _route_baseline(offer)
            if not _trusted(route_base) or not route_base.median:
                continue
            discount = (route_base.median - offer.price) / route_base.median
            severity = _classify(discount, config)
            if severity:
                cheap_dates.append(Deal(
                    offer=offer,
                    baseline=route_base,
                    discount_pct=round(discount, 4),
                    saving=round(route_base.median - offer.price, 2),
                    severity=severity,
                    city=route.city,
                    basis="route",
                    basis_samples=route_base.samples,
                ))

        # One alert per route. A confirmed drop always beats a merely cheap
        # date, however large the latter's headline discount looks.
        pool = drops or cheap_dates
        if pool:
            deals.append(max(pool, key=lambda d: d.discount_pct))

    # Confirmed drops first, then by size of discount.
    deals.sort(key=lambda d: (d.is_price_drop, d.discount_pct), reverse=True)
    return deals, summaries
