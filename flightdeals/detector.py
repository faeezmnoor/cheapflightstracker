"""Turn raw offers + history into deals and a per-route digest."""

from __future__ import annotations

from datetime import date
from typing import Dict, List

from .baseline import baselines_by_route
from .config import Config, Route
from .models import Baseline, Deal, Offer, RouteSummary


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

    for route in routes:
        offers = sorted(offers_by_route.get(route.key, []), key=lambda o: o.price)
        baseline = baselines.get(route.key, Baseline(route.key, 0))

        cheapest = offers[0] if offers else None
        # Only report an "off usual" figure once the baseline is trustworthy
        # (same bar as deal detection), so thin history can't imply a discount.
        baseline_trusted = (
            baseline.is_reliable
            and baseline.median
            and baseline.samples >= config.min_samples
        )
        summary_discount = None
        if cheapest and baseline_trusted:
            summary_discount = round(
                (baseline.median - cheapest.price) / baseline.median, 4
            )
        summaries.append(RouteSummary(
            route_key=route.key,
            city=route.city,
            cheapest=cheapest,
            baseline=baseline,
            discount_pct=summary_discount,
        ))

        # Only flag deals once we have enough history to trust the baseline.
        if not baseline.is_reliable or baseline.samples < config.min_samples:
            continue
        if not baseline.median:
            continue

        for offer in offers:
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
            # One deal per route/date is enough; the cheapest is listed first,
            # so once a route qualifies we don't spam every fare on it.
            break

    # Best discounts first; severe deals naturally sort to the top.
    deals.sort(key=lambda d: d.discount_pct, reverse=True)
    return deals, summaries
