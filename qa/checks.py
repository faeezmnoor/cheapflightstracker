"""The checks themselves — each one derived from a defect that actually shipped.

Every check carries the incident that motivated it. That is not decoration:
a check nobody can trace to a real failure tends to get relaxed the first time
it is inconvenient, and this suite exists precisely because plausible-looking
output kept passing a green test suite.

The digest checks (C*) read the run's own claims and re-derive them from raw
history. The data checks (D*) look at the price history itself, where the
failures are about *absence* — a run that never happened, a route that has
quietly returned nothing for a week.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from .findings import BLOCK, INFO, WARN, AuditReport, Finding
from .recompute import baseline_for, discount_vs, percentile_of

# --------------------------------------------------------------------------- #
# Tolerances
# --------------------------------------------------------------------------- #
# Prices are rounded to 2dp on both sides, so an exact match is expected; the
# tolerance exists to absorb rounding, not to excuse a different method.
REL_TOLERANCE = 0.005          # 0.5%
ABS_TOLERANCE = 0.51           # currency units

# More than this fraction of routes alerting on one morning has never once been
# a genuine market event. It has twice been a methodology bug.
MAX_ALERT_RATE = 0.30

# ...but a rate over a handful of routes carries no information: one alert out
# of two routes is 50% and means nothing. The rate check only speaks when the
# denominator can support it, which also keeps small custom route lists and the
# test fixtures from tripping it.
MIN_ROUTES_FOR_RATE = 8
MIN_ALERTS_FOR_RATE = 3

# A fare moving more than this multiple day-over-day is a scrape artifact far
# more often than a real repricing.
SWING_FACTOR = 3.0

# How many consecutive silent days before a route is presumed dead.
DEAD_ROUTE_DAYS = 5

# A few empty routes is ordinary — some have no service on some days.
# Past this share, the common cause is the provider, not the airlines.
MAX_EMPTY_ROUTE_RATE = 0.5


def _close(a: Optional[float], b: Optional[float]) -> bool:
    if a is None or b is None:
        return a is b
    return abs(a - b) <= max(ABS_TOLERANCE, abs(b) * REL_TOLERANCE)


def _money(value: Optional[float], currency: str = "") -> str:
    if value is None:
        return "n/a"
    return f"{currency} {value:,.2f}".strip()


# --------------------------------------------------------------------------- #
# Digest checks — is what the email says true?
# --------------------------------------------------------------------------- #
def check_alert_matches_table(digest: dict, report: AuditReport) -> None:
    """C1 — an alert may never quote a price worse than the table beneath it.

    Incident (12 Aug): an alert announced KL->Pontianak at 309 while the
    cheapest-today table on the same email showed 279 for that route. The
    detector was picking the *biggest discount* across 30 departure dates
    rather than the route's cheapest fare, so the two disagreed by design.
    """
    report.ran("C1")
    by_route = {s["route_key"]: s for s in digest.get("summaries", [])}
    for deal in digest.get("deals", []):
        summary = by_route.get(deal["route_key"])
        if not summary or summary.get("price") is None:
            report.add(Finding(
                "C1", BLOCK, "alerted route is missing from the digest table",
                route_key=deal["route_key"]))
            continue
        if deal["price"] > summary["price"] + ABS_TOLERANCE:
            report.add(Finding(
                "C1", BLOCK,
                "alert quotes a worse price than the table shows",
                evidence=(f"alert {_money(deal['price'])} vs table "
                          f"{_money(summary['price'])}"),
                route_key=deal["route_key"]))


def check_alert_rate(digest: dict, report: AuditReport) -> None:
    """C2 — a morning where most routes are "underpriced" is a broken baseline.

    Incident (12 Aug): 21 of 26 routes alerted at once, after MIN_DATE_SAMPLES
    was lowered to 1 and single noisy readings became baselines. The digest
    read as a once-in-a-decade sale; it was arithmetic on garbage.
    """
    report.ran("C2")
    routes = len(digest.get("summaries", []))
    alerts = len(digest.get("deals", []))
    if routes < MIN_ROUTES_FOR_RATE or alerts < MIN_ALERTS_FOR_RATE:
        return
    if alerts / routes > MAX_ALERT_RATE:
        report.add(Finding(
            "C2", BLOCK,
            "implausible share of routes flagged as underpriced",
            evidence=(f"{alerts}/{routes} routes = "
                      f"{alerts / routes:.0%} (ceiling {MAX_ALERT_RATE:.0%})")))


def check_baseline_thickness(digest: dict, report: AuditReport) -> None:
    """C3 — no alert may rest on fewer days than the configured minimum.

    Incident (12 Aug): a single prior reading of 2,110 on KL->Batam produced an
    "85% off" alert. One observation is not a baseline, it is an anecdote.
    """
    report.ran("C3")
    minimum = int(digest.get("min_samples") or 0)
    for deal in digest.get("deals", []):
        samples = int(deal.get("samples") or 0)
        if samples < minimum:
            report.add(Finding(
                "C3", BLOCK, "alert rests on too little history",
                evidence=f"{samples} day(s) of history, minimum is {minimum}",
                route_key=deal["route_key"]))


def check_arithmetic(digest: dict, report: AuditReport) -> None:
    """C4 — the discount, the saving and the two prices must agree.

    No single incident: this is the check that makes the *other* checks
    meaningful, because it pins the numbers in the email to each other. If a
    future change renders one figure from a different source than another, the
    email starts quietly contradicting itself.
    """
    report.ran("C4")
    for deal in digest.get("deals", []):
        median_price, price = deal.get("median"), deal.get("price")
        if median_price is None or price is None:
            report.add(Finding("C4", BLOCK, "alert is missing its own numbers",
                               route_key=deal["route_key"]))
            continue
        if not _close(deal.get("saving"), median_price - price):
            report.add(Finding(
                "C4", BLOCK, "stated saving does not match the prices shown",
                evidence=(f"saving {_money(deal.get('saving'))} but "
                          f"{_money(median_price)} - {_money(price)} = "
                          f"{_money(median_price - price)}"),
                route_key=deal["route_key"]))
        expected = discount_vs(median_price, price)
        if not _close(deal.get("discount_pct"), expected):
            report.add(Finding(
                "C4", BLOCK, "stated discount does not match the prices shown",
                evidence=(f"claims {deal.get('discount_pct')}, prices imply "
                          f"{expected:.4f}" if expected is not None else ""),
                route_key=deal["route_key"]))


def check_baseline_independently(digest: dict, history: List[dict],
                                 report: AuditReport) -> None:
    """C5 — recompute every claimed baseline from raw history and compare.

    This is the check the whole package exists for, and it covers two separate
    incidents at once:

    * One-way and round-trip fares once shared a baseline. A return costs about
      double, so the pooled median sat between them and every one-way looked
      ~50% underpriced. Recomputing *per trip type* disagrees loudly.
    * The baseline once averaged every offer seen rather than each day's
      cheapest. Most offers on a day are worse than that day's best, so the
      baseline drifted upward and made ordinary fares look like deals.

    Either bug returns a median that this independent derivation will not
    reproduce, whatever the detector believes.
    """
    report.ran("C5")
    run_date = digest.get("run_date")
    for deal in digest.get("deals", []):
        truth = baseline_for(history, deal["route_key"],
                             deal.get("trip_type") or "one_way", run_date)
        if truth["median"] is None:
            report.add(Finding(
                "C5", BLOCK,
                "alert has no supporting history for its own trip type",
                evidence=f"trip_type={deal.get('trip_type')}",
                route_key=deal["route_key"]))
            continue
        if not _close(deal.get("median"), truth["median"]):
            report.add(Finding(
                "C5", BLOCK,
                "claimed usual price does not match the price history",
                evidence=(f"digest says {_money(deal.get('median'))}, history "
                          f"gives {_money(truth['median'])} over "
                          f"{truth['samples']} day(s)"),
                route_key=deal["route_key"]))
        if int(deal.get("samples") or 0) != truth["samples"]:
            report.add(Finding(
                "C5", WARN, "claimed sample count does not match history",
                evidence=(f"digest says {deal.get('samples')}, history has "
                          f"{truth['samples']}"),
                route_key=deal["route_key"]))
        # A "new low" that is not actually below the recorded minimum is the
        # strongest claim the email makes, so it gets checked hardest.
        if deal.get("is_new_low") and truth["minimum"] is not None:
            if deal["price"] >= truth["minimum"]:
                report.add(Finding(
                    "C5", BLOCK, "claims a new low that is not a new low",
                    evidence=(f"{_money(deal['price'])} vs recorded minimum "
                              f"{_money(truth['minimum'])}"),
                    route_key=deal["route_key"]))
        claimed = deal.get("percentile")
        actual = percentile_of(list(truth["series"].values()), deal["price"])
        if claimed is not None and actual is not None and abs(claimed - actual) > 0.05:
            report.add(Finding(
                "C5", WARN, "claimed rarity does not match history",
                evidence=f"digest says {claimed:.0%}, history gives {actual:.0%}",
                route_key=deal["route_key"]))


def check_currency(digest: dict, report: AuditReport) -> None:
    """C6 — one run, one currency.

    Not yet an incident, but the point-of-sale parameters (``gl``/``hl``/
    ``curr``) are already per-request, and a partially applied change would mix
    MYR and USD figures into one table where they would silently be compared.
    """
    report.ran("C6")
    expected = digest.get("currency")
    rows = digest.get("deals", []) + digest.get("summaries", [])
    odd = {r.get("currency") for r in rows if r.get("currency")} - {expected, None}
    if odd:
        report.add(Finding(
            "C6", BLOCK, "digest mixes currencies",
            evidence=f"run currency {expected}, also found {sorted(odd)}"))


def check_presentation(digest: dict, html: Optional[str],
                       report: AuditReport) -> None:
    """C7 — what was rendered matches what was computed.

    Incident (12 Aug): two attempted edits to add map links silently matched
    nothing and were never applied. The unit tests still passed, the email
    still sent, and the feature simply was not there — caught only by counting
    the links in the rendered HTML.
    """
    report.ran("C7")
    if not html:
        return
    expected_links = len(digest.get("summaries", [])) + len(digest.get("deals", []))
    found = html.count("maps/search")
    if expected_links and found < expected_links:
        report.add(Finding(
            "C7", WARN, "rendered digest is missing map links",
            evidence=f"expected {expected_links}, rendered {found}"))
    # The headline price must survive rendering. A deal present in the data but
    # absent from the HTML means the template dropped it.
    for deal in digest.get("deals", []):
        price = f"{deal['price']:,.2f}"
        if price not in html and f"{deal['price']:,.0f}" not in html:
            report.add(Finding(
                "C7", WARN, "alert price does not appear in the rendered email",
                evidence=f"looked for {price}", route_key=deal["route_key"]))


# --------------------------------------------------------------------------- #
# Data checks — is the history underneath it sound?
# --------------------------------------------------------------------------- #
def _observation_days(history: List[dict]) -> List[str]:
    return sorted({o["observed_date"] for o in history if o.get("observed_date")})


def check_freshness(history: List[dict], run_date: str,
                    report: AuditReport) -> None:
    """D1 — the history must actually reach yesterday.

    Incident (13 Aug): renaming the default branch dropped the cron
    registration. No run fired, no failure was reported, and the first signal
    was a human noticing the email had not arrived. Nothing inside a run can
    detect a run that never happened — but the *next* run can, and so can a
    scheduled audit.
    """
    report.ran("D1")
    days = _observation_days(history)
    if not days:
        report.add(Finding("D1", BLOCK, "price history is empty"))
        return
    try:
        gap = (date.fromisoformat(run_date) - date.fromisoformat(days[-1])).days
    except ValueError:
        return
    if gap > 1:
        report.add(Finding(
            "D1", WARN, "price history has gone stale — a run was missed",
            evidence=(f"latest observation {days[-1]}, {gap} day(s) before "
                      f"{run_date}")))


def check_continuity(history: List[dict], run_date: str, window: int,
                     report: AuditReport) -> None:
    """D2 — no missing days inside the recent window.

    Same incident as D1, seen from the other side: one absent day is a skipped
    run, and every absent day silently thins the baselines that decide alerts.
    """
    report.ran("D2")
    days = set(_observation_days(history))
    if not days:
        return
    try:
        today = date.fromisoformat(run_date)
    except ValueError:
        return
    expected = [(today - timedelta(days=n)).isoformat()
                for n in range(1, window + 1)]
    # Only count days after tracking actually began, or every check would
    # report the whole pre-history as missing.
    started = min(days)
    missing = [d for d in expected if d >= started and d not in days]
    if missing:
        report.add(Finding(
            "D2", WARN, "days missing from the price history",
            evidence=f"{len(missing)} missing in last {window}: "
                     f"{', '.join(sorted(missing)[:6])}"))


def check_dead_routes(history: List[dict], digest: dict, run_date: str,
                      report: AuditReport) -> None:
    """D3 — a route that has returned nothing for days is misconfigured.

    Incident (early Aug): Yogyakarta was configured as JOG, which handles only
    domestic traffic, so the route returned nothing every single day. It never
    errored — it was simply, permanently, empty, and went unnoticed because an
    empty route looks exactly like a route with no cheap fares.
    """
    report.ran("D3")
    try:
        cutoff = (date.fromisoformat(run_date)
                  - timedelta(days=DEAD_ROUTE_DAYS)).isoformat()
    except ValueError:
        return
    recent = {f"{o.get('origin')}-{o.get('destination')}" for o in history
              if (o.get("observed_date") or "") >= cutoff}
    if not recent:
        return          # nothing recent at all is D1's story, not this one
    ever = {f"{o.get('origin')}-{o.get('destination')}" for o in history}

    # Two different diagnoses, and the distinction matters: a route that has
    # *never* returned a fare is usually a wrong airport code (JOG is domestic
    # only), while one that used to work and stopped is usually the route being
    # withdrawn or the scraper being blocked.
    never, went_silent = [], []
    for summary in digest.get("summaries", []):
        key = summary["route_key"]
        if key in recent or summary.get("price") is not None:
            continue
        (went_silent if key in ever else never).append(key)

    # Aggregated into one finding each: a systemic fault affects every route at
    # once, and thirty identical lines bury the one that matters.
    if never:
        report.add(Finding(
            "D3", WARN, "route has never returned a fare — check the airport "
                        "code serves this origin",
            evidence=f"{len(never)}: {', '.join(sorted(never))}"))
    if went_silent:
        report.add(Finding(
            "D3", WARN, f"route has returned nothing for {DEAD_ROUTE_DAYS}+ "
                        f"days after previously working",
            evidence=f"{len(went_silent)}: {', '.join(sorted(went_silent))}"))


def check_window_is_exhaustive(digest: dict, report: AuditReport) -> None:
    """D4 — every date in the window must be probed, not a sample of them.

    Incident (early Aug): only two departure dates per route were being
    searched. Google prices each date separately, so a date not probed is a
    price that cannot be seen — the user found a 339 fare on Google that the
    digest had no way of knowing about.
    """
    report.ran("D4")
    scanned = digest.get("scanned_departures") or []
    expected = int(digest.get("departure_window_days") or 0)
    if expected and len(set(scanned)) < expected:
        report.add(Finding(
            "D4", WARN, "departure window was not scanned exhaustively",
            evidence=f"probed {len(set(scanned))} of {expected} dates"))


def check_coverage(digest: dict, report: AuditReport) -> None:
    """D6 — most routes coming back empty at once is an outage, not a market.

    Not yet an incident, but the nearest miss in the design: if the provider
    breaks — Google changes the page format, or the runner's IP is throttled —
    every route returns nothing, the digest sends an empty table, and *no other
    check fires*. Alerts are absent rather than wrong, the history simply is not
    written, and D1 only notices tomorrow.

    An individual empty route is ordinary. Most of them at once never is.
    """
    report.ran("D6")
    summaries = digest.get("summaries", [])
    if len(summaries) < MIN_ROUTES_FOR_RATE:
        return
    empty = [s for s in summaries if s.get("price") is None]
    if len(empty) / len(summaries) > MAX_EMPTY_ROUTE_RATE:
        report.add(Finding(
            "D6", WARN,
            "most routes returned no fares — suspect a provider outage or a "
            "throttled runner, not a quiet market",
            evidence=f"{len(empty)}/{len(summaries)} routes empty"))


def check_price_swings(history: List[dict], digest: dict, run_date: str,
                       report: AuditReport) -> None:
    """D5 — flag implausible day-over-day moves as suspected scrape noise.

    Incident (11-12 Aug): roughly 7% of departure dates swung more than 2x
    overnight, almost always because a scrape missed the cheap itineraries and
    recorded a much higher floor. This is informational by design — it is how
    we know how much to distrust a thin baseline, and it was the evidence that
    demoted per-date comparisons from alert-worthy to annotation-only.
    """
    report.ran("D5")
    noisy = []
    for summary in digest.get("summaries", []):
        if summary.get("price") is None:
            continue
        series = baseline_for(history, summary["route_key"],
                              summary.get("trip_type") or "one_way",
                              run_date)["series"]
        if not series:
            continue
        previous = series[max(series)]
        price = summary["price"]
        if previous <= 0 or price <= 0:
            continue
        ratio = max(price / previous, previous / price)
        if ratio >= SWING_FACTOR:
            noisy.append(f"{summary['route_key']} {previous:,.0f}->{price:,.0f}")
    if noisy:
        report.add(Finding(
            "D5", INFO, "large overnight price moves — possible scrape noise",
            evidence="; ".join(noisy[:6])))


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def audit(digest: dict, history: List[dict], html: Optional[str] = None,
          continuity_window: int = 7) -> AuditReport:
    """Run every check. ``history`` must be the state *before* this run's
    observations were appended, exactly as the detector saw it."""
    report = AuditReport()
    run_date = digest.get("run_date") or datetime.utcnow().date().isoformat()

    check_alert_matches_table(digest, report)
    check_alert_rate(digest, report)
    check_baseline_thickness(digest, report)
    check_arithmetic(digest, report)
    check_baseline_independently(digest, history, report)
    check_currency(digest, report)
    check_presentation(digest, html, report)

    check_freshness(history, run_date, report)
    check_continuity(history, run_date, continuity_window, report)
    check_dead_routes(history, digest, run_date, report)
    check_window_is_exhaustive(digest, report)
    check_coverage(digest, report)
    check_price_swings(history, digest, run_date, report)
    return report


def summarise_checks() -> Dict[str, str]:
    """Check id -> one-line purpose, for docs and CI summaries."""
    return {
        "C1": "alert never quotes a worse price than the table",
        "C2": "share of routes alerting stays plausible",
        "C3": "no alert rests on fewer days than MIN_SAMPLES",
        "C4": "discount, saving and prices agree with each other",
        "C5": "claimed baselines reproduce from raw history",
        "C6": "one run, one currency",
        "C7": "what was rendered matches what was computed",
        "D1": "history reaches yesterday (a run actually happened)",
        "D2": "no missing days inside the recent window",
        "D3": "no route silently returning nothing for days",
        "D4": "departure window scanned exhaustively, not sampled",
        "D5": "implausible overnight moves surfaced as noise",
        "D6": "most routes empty at once means a provider outage",
    }
