"""Turn raw offers + history into deals and a per-route digest."""

from __future__ import annotations

from datetime import date
from typing import Dict, List

from .baseline import baselines_by_route
from .config import Config, Route
from .models import Baseline, Deal, Offer, RouteSummary  # noqa: F401


def _classify(discount_pct: float, config: Config) -> str | None:
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
) -> tuple[List[Deal], List[RouteSummary]]:
    """Compare today's offers to the baseline built from prior history.

    ``history`` must be the *prior* record list (before today's observations
    are appended), so the baseline reflects the usual price.
    """
    route_meta = {r.key: r for r in routes}
    baselines = baselines_by_route(
        history, route_meta.keys(), config.history_window_days, today
    )

    deals: List[Deal] = []
    summaries: List[RouteSummary] = []

    def _baseline_for(offer: Offer) -> Baseline:
        key = (offer.route_key, offer.trip_type)
        return baselines.get(key, Baseline(offer.route_key, 0, offer.trip_type))

    def _trusted(baseline: Baseline) -> bool:
        # Same bar for the digest and for alerts, so thin history can never
        # imply a discount.
        return bool(baseline.is_reliable and baseline.median
                    and baseline.samples >= config.min_samples)

    for route in routes:
        offers = sorted(offers_by_route.get(route.key, []), key=lambda o: o.price)

        cheapest = offers[0] if offers else None
        # Compare the headline fare against its own trip type's baseline.
        summary_baseline = (_baseline_for(cheapest) if cheapest
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
        ))

        for offer in offers:
            baseline = _baseline_for(offer)
            if not _trusted(baseline) or not baseline.median:
                continue
            discount = (baseline.median - offer.price) / baseline.median
            severity = _classify(discount, config)
            if severity is None:
                continue
            deals.append(Deal(
                offer=offer,
                baseline=baseline,
                discount_pct=round(discount, 4),
                saving=round(baseline.median - offer.price, 2),
                severity=severity,
            ))
            # One deal per route is enough; offers are cheapest-first, so we
            # report the best and don't spam every fare on the route.
            break

    # Best discounts first; severe deals naturally sort to the top.
    deals.sort(key=lambda d: d.discount_pct, reverse=True)
    return deals, summaries
