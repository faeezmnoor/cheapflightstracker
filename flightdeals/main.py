"""Entry point: run a daily scan end-to-end, in one process or sharded.

Single process (small route lists, local runs):

    load config -> search every route/date -> compute baselines from prior
    history -> flag deals -> email digest -> persist today's cheapest fares.

Sharded (CI, many routes): several scan shards run in parallel, each writing
its offers to a file, then one report step merges them and does the rest.

    python run.py --shard 0 --shards 4 --output obs-0.json     # per shard
    python run.py --report obs-*.json                          # once, after
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import date, datetime, timezone
from typing import Dict, List

from .baseline import (append_observations, daily_cheapest,
                       daily_cheapest_by_date, load_alert_state,
                       load_date_series, load_history, prune_date_series,
                       prune_history, record_date_prices, save_alert_state,
                       save_date_series, save_history)
from .artifact import digest_payload, write_digest
from .config import Config, shard_routes
from .detector import find_deals
from .emailer import build_html, send_email
from .models import Offer, RunResult
from .providers import get_provider
from .search import plan_date_pairs, run_searches


# --------------------------------------------------------------------------- #
# Scanning
# --------------------------------------------------------------------------- #
def scan(config: Config, today: date) -> tuple[Dict[str, List[Offer]], List[str]]:
    """Search every route x date for this config's routes."""
    print(f"[scan] {today.isoformat()} | provider={config.provider} | "
          f"routes={len(config.routes)} | currency={config.currency}")
    provider = get_provider(config)
    offers_by_route, errors = run_searches(provider, config, today)
    checked = sum(len(v) for v in offers_by_route.values())
    print(f"[scan] collected {checked} offers, {len(errors)} error(s)")
    for err in errors[:8]:
        print(f"[scan]   ! {err}")
    if len(errors) > 8:
        print(f"[scan]   ! ...and {len(errors) - 8} more")
    empty = [r.label for r in config.routes if not offers_by_route.get(r.key)]
    if empty:
        print(f"[scan] routes with no offers: {', '.join(empty)}")
    return offers_by_route, errors


def write_shard(path: str, today: date, offers_by_route: Dict[str, List[Offer]],
                errors: List[str], config: Config) -> None:
    """Persist a shard's findings for the report step to pick up."""
    payload = {
        "run_date": today.isoformat(),
        "errors": errors,
        "scanned_departures": sorted({d for d, _ in plan_date_pairs(config, today)}),
        # How many fares were actually examined, before compaction — the
        # digest reports this, not the handful of survivors.
        "offers_scanned": sum(len(v) for v in offers_by_route.values()),
        # Cheapest per departure date (not merely per route): the per-date
        # series needs them, and the route-level cheapest is just the min of
        # these. Still a tiny fraction of the thousands of raw offers.
        "offers": [o.to_record() for o in daily_cheapest_by_date(
            o for v in offers_by_route.values() for o in v)],
    }
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
    print(f"[scan] wrote {len(payload['offers'])} per-date cheapest fares "
          f"-> {path}")


def read_shards(patterns: List[str]) -> tuple[Dict[str, List[Offer]], List[str],
                                              List[str], str | None, int]:
    """Merge shard files back into offers/errors/scanned dates."""
    paths: List[str] = []
    for pattern in patterns:
        paths.extend(sorted(glob.glob(pattern)))
    if not paths:
        raise SystemExit(f"[fatal] no shard files matched: {patterns}")

    offers_by_route: Dict[str, List[Offer]] = {}
    errors: List[str] = []
    scanned: set[str] = set()
    run_date = None
    scanned_count = 0
    for path in paths:
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        run_date = run_date or payload.get("run_date")
        errors.extend(payload.get("errors") or [])
        scanned.update(payload.get("scanned_departures") or [])
        scanned_count += int(payload.get("offers_scanned") or 0)
        for record in payload.get("offers") or []:
            offer = Offer.from_record(record)
            offers_by_route.setdefault(offer.route_key, []).append(offer)
        print(f"[report] loaded {len(payload.get('offers') or [])} fares "
              f"from {path}")
    return offers_by_route, errors, sorted(scanned), run_date, scanned_count


# --------------------------------------------------------------------------- #
# Quality gate
# --------------------------------------------------------------------------- #
def _qa_gate(result: RunResult, history: List[dict], config: Config) -> None:
    """Audit the digest before it is sent, and withhold alerts that fail.

    The gate degrades rather than aborts: a blocking finding means the
    *statistics* are untrustworthy, not that today's fares are. Suppressing the
    alerts while still sending the cheapest-today table keeps the useful half
    of the email and makes the failure visible, which is the opposite of every
    incident this project has had — all of which shipped confident, wrong
    numbers to an inbox and were caught days later by a human.

    Imported lazily so the QA package stays an optional add-on: a checkout
    without it still sends mail rather than crashing at the last step.
    """
    try:
        from qa.checks import audit
    except ImportError:                                  # pragma: no cover
        print("[qa] auditor unavailable — sending unaudited")
        return

    html = build_html(result)
    payload = digest_payload(result, config)
    report_ = audit(payload, history, html)
    print(f"[qa] {report_.render()}")

    if config.digest_artifact_path:
        write_digest(config.digest_artifact_path, result, html, config,
                     qa=report_.findings)

    if report_.blocking:
        # De-duplicate: one line per distinct problem, not one per route, or a
        # systemic fault fills the banner with thirty identical sentences.
        reasons: List[str] = []
        for finding in report_.blocking:
            reason = finding.message
            if reason not in reasons:
                reasons.append(reason)
        print(f"[qa] withholding {len(result.deals)} alert(s): "
              f"{len(report_.blocking)} blocking finding(s)")
        result.qa_withheld = reasons
        result.deals = []


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def report(config: Config, today: date,
           offers_by_route: Dict[str, List[Offer]], errors: List[str],
           scanned: List[str], offers_checked: int) -> RunResult:
    """Compare against history, email the digest, then persist today's fares."""
    # Baselines must reflect PRIOR history, so evaluate before appending.
    history = load_history(config.history_path)
    series = load_date_series(config.date_history_path)
    alerts = load_alert_state(config.alert_state_path)
    deals, summaries = find_deals(
        offers_by_route, history, config.routes, config, today, series, alerts,
        scanned_departures=scanned,
    )
    drops = sum(1 for d in deals if d.is_price_drop)
    print(f"[report] flagged {len(deals)} deal(s): "
          f"{drops} confirmed price drop(s), {len(deals) - drops} cheap date(s)")

    # The far-horizon lane, if it has been scanned. Compared against this run's
    # near-window cheapest, and never pooled into the route baselines — a fare
    # 150 days out belongs to a different population, and mixing the two is the
    # error that made every one-way look half price when returns shared a
    # baseline. Optional: a checkout that has never run the weekly scan simply
    # has nothing to show here.
    horizon_finds: List[object] = []
    try:
        from .horizon import find_bargains, load_horizon
        near = {s.route_key: s.cheapest.price for s in summaries if s.cheapest}
        horizon_finds = find_bargains(
            load_horizon(config.horizon_path), near, today,
            config.horizon_min_discount,
            cities={r.key: r.city for r in config.routes},
            maps_urls={r.key: r.maps_url for r in config.routes},
            currency=config.currency)
        if horizon_finds:
            print(f"[report] {len(horizon_finds)} route(s) cheaper further out")
    except Exception as exc:                              # noqa: BLE001
        print(f"[report] horizon lane unavailable: {exc!r}")

    result = RunResult(
        run_date=today.isoformat(),
        currency=config.currency,
        deals=deals,
        summaries=summaries,
        offers_checked=offers_checked,
        errors=errors,
        scanned_departures=scanned,
        horizon=horizon_finds,
    )

    # QA runs *before* the send, so a wrong alert is caught rather than
    # delivered. It is deliberately given `history` — the state the detector
    # saw — and re-derives every claim from it independently.
    _qa_gate(result, history, config)

    send_email(result, config)

    # A dry run is a preview, and a preview must not change the thing it is
    # previewing. This used to persist regardless of the flag, so
    # `--provider mock --dry-run` wrote invented fares straight into the real
    # price history — corrupting the baselines that every future alert is
    # judged against, from a command whose entire purpose is to be harmless.
    if config.dry_run:
        print("[report] dry run — history, date series and alert state "
              "left untouched")
        return result

    all_offers = [o for v in offers_by_route.values() for o in v]
    per_date = daily_cheapest_by_date(all_offers)

    # Route-level history: one row per route/trip-type, for the "usual
    # cheapest" baseline and the digest.
    #
    # Routes whose scan came back thin are left out. Their "cheapest" is the
    # minimum of a handful of dates, which systematically over-estimates — on
    # 17 Aug KL->Ambon recorded 1,787 off a single date against 794 the day
    # before. Writing that into history does lasting damage: it raises the
    # median, and a normal fare tomorrow then reads as a deal.
    thin = {s.route_key for s in summaries
            if s.dates_scanned and s.dates_seen
            < s.dates_scanned * config.min_date_coverage}
    keep = [o for o in daily_cheapest(per_date) if o.route_key not in thin]
    if thin:
        print(f"[report] {len(thin)} route(s) had too few departure dates to "
              f"record: {', '.join(sorted(thin))}")
    history = append_observations(history, keep, today.isoformat())
    history = prune_history(history, config.history_window_days + 30, today)
    save_history(config.history_path, history)

    # Per-date series: lets tomorrow tell a real price drop from a cheap date
    # that has only just scrolled into the window.
    series = record_date_prices(series, per_date, today.isoformat())
    series = prune_date_series(series, today)
    save_date_series(config.date_history_path, series)

    # Remember what was sent so tomorrow can tell repetition from news.
    for deal in deals:
        alerts[deal.offer.route_key] = {
            "price": deal.offer.price,
            "date": today.isoformat(),
            "departure_date": deal.offer.departure_date,
        }
    save_alert_state(config.alert_state_path, alerts)

    print(f"[report] history: {len(history)} route observations, "
          f"{len(series)} date series -> {config.history_path}, "
          f"{config.date_history_path}")
    return result


def run(config: Config, today: date | None = None) -> RunResult:
    """Single-process scan + report (no sharding)."""
    today = today or datetime.now(timezone.utc).date()
    offers_by_route, errors = scan(config, today)
    checked = sum(len(v) for v in offers_by_route.values())
    scanned = sorted({d for d, _ in plan_date_pairs(config, today)})
    return report(config, today, offers_by_route, errors, scanned, checked)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Daily KL->Indonesia flight-deal scan")
    parser.add_argument("--provider", help="Override PROVIDER (googleflights|mock)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the email instead of sending it")
    parser.add_argument("--date", help="Override 'today' as YYYY-MM-DD (testing)")
    parser.add_argument("--shard", type=int, help="This shard's index (0-based)")
    parser.add_argument("--shards", type=int, default=1,
                        help="Total number of scan shards")
    parser.add_argument("--output", help="Scan only; write findings here")
    parser.add_argument("--report", nargs="+", metavar="FILE",
                        help="Report only; merge these shard files")
    args = parser.parse_args(argv)

    config = Config.from_env()
    if args.provider:
        config.provider = args.provider
    if args.dry_run:
        config.dry_run = True
    today = (datetime.strptime(args.date, "%Y-%m-%d").date() if args.date
             else datetime.now(timezone.utc).date())

    try:
        if args.report:
            offers, errors, scanned, run_date, checked = read_shards(args.report)
            if run_date and not args.date:
                today = datetime.strptime(run_date, "%Y-%m-%d").date()
            report(config, today, offers, errors, scanned,
                   checked or sum(len(v) for v in offers.values()))
        elif args.output:
            if args.shard is not None:
                config.routes = shard_routes(config.routes, args.shard, args.shards)
                print(f"[scan] shard {args.shard}/{args.shards}: "
                      f"{[r.destination for r in config.routes]}")
            offers, errors = scan(config, today)
            write_shard(args.output, today, offers, errors, config)
        else:
            run(config, today)
    except Exception as exc:  # noqa: BLE001
        print(f"[fatal] {exc!r}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
