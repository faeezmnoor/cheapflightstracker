#!/usr/bin/env python3
"""Send a digest rebuilt from recorded history, writing nothing.

For seeing an email-template change in a real inbox without re-scanning and
without touching state. A normal run would do three things this must not:
burn ~780 live searches against a provider that is already throttling us,
append a second set of observations for a day that already has one, and update
the alert state so tomorrow's genuine alert gets suppressed as a repeat.

    python scripts/send_preview.py                    # most recent recorded day
    python scripts/send_preview.py --date 2026-08-16  # a day with a real alert

Subject is prefixed so it can never be mistaken for the morning digest — two
emails that look alike but disagree is a confusion this project has already
caused once.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flightdeals.baseline import load_date_series
from flightdeals.config import Config
from flightdeals.detector import find_deals
from flightdeals.emailer import build_html, build_subject, build_text
from flightdeals.models import RunResult
from flightdeals.search import plan_date_pairs
from replay_audit import load_observations, offers_from_series


def build(config: Config, run_date: str) -> RunResult:
    observations = load_observations(config.history_path)
    series = load_date_series(config.date_history_path)
    prior = [o for o in observations
             if (o.get("observed_date") or "") < run_date]
    offers = offers_from_series(series, run_date)
    if not offers:
        raise SystemExit(f"[preview] no recorded per-date fares for {run_date}")

    by_route: dict = {}
    for offer in offers:
        by_route.setdefault(offer.route_key, []).append(offer)

    as_date = date.fromisoformat(run_date)
    scanned = sorted({d for d, _ in plan_date_pairs(config, as_date)})
    # Repeat-suppression is passed empty on purpose: this is a preview of how a
    # digest renders, not a decision about what is news, and reading the real
    # alert state would make the preview depend on what was sent this morning.
    deals, summaries = find_deals(by_route, prior, config.routes, config,
                                  as_date, series, {},
                                  scanned_departures=scanned)

    horizon: List[object] = []
    try:
        from flightdeals.horizon import find_bargains, load_horizon
        near = {s.route_key: (s.cheapest.price, s.dates_seen, s.dates_scanned)
                for s in summaries if s.cheapest}
        horizon = find_bargains(
            load_horizon(config.horizon_path), near, as_date,
            config.horizon_block_starts, config.horizon_block_days,
            config.horizon_min_discount, config.horizon_min_coverage,
            cities={r.key: r.city for r in config.routes},
            maps_urls={r.key: r.maps_url for r in config.routes},
            currency=config.currency)
    except Exception as exc:                              # noqa: BLE001
        print(f"[preview] horizon lane unavailable: {exc!r}")

    print(f"[preview] {run_date}: {len(deals)} alert(s), {len(summaries)} "
          f"routes, {len(horizon)} horizon find(s)")
    if not horizon:
        print("[preview] no 'cheaper if you fly later' section — the weekly "
              "horizon scan has not run yet, so there is nothing to compare")
    return RunResult(run_date, config.currency, deals, summaries, len(offers),
                     [], scanned_departures=scanned, horizon=horizon)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="which recorded day to rebuild")
    parser.add_argument("--print", action="store_true",
                        help="print instead of sending")
    args = parser.parse_args(argv)

    config = Config.from_env()
    config.dry_run = False          # this script's whole job is to send
    config.always_email = True      # ...even on a day with no alerts

    run_date = args.date
    if not run_date:
        days = sorted({o["observed_date"]
                       for o in load_observations(config.history_path)
                       if o.get("observed_date")})
        if not days:
            raise SystemExit("[preview] no recorded history")
        run_date = days[-1]

    result = build(config, run_date)

    # Never let a preview be mistaken for the morning digest.
    subject = "[PREVIEW] " + build_subject(result)
    if args.print:
        print(f"Subject: {subject}\n")
        print(build_text(result))
        return 0

    import smtplib
    import ssl
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    missing = [n for n, v in {"SMTP_USER": config.smtp_user,
                              "SMTP_APP_PASSWORD": config.smtp_app_password,
                              "EMAIL_TO": config.email_to}.items() if not v]
    if missing:
        raise SystemExit(f"[preview] missing {', '.join(missing)}")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.email_from or config.smtp_user
    msg["To"] = config.email_to
    msg.attach(MIMEText(build_text(result), "plain", "utf-8"))
    msg.attach(MIMEText(build_html(result), "html", "utf-8"))
    with smtplib.SMTP_SSL(config.smtp_host, config.smtp_port,
                          context=ssl.create_default_context()) as server:
        server.login(config.smtp_user, config.smtp_app_password)
        server.sendmail(msg["From"], [config.email_to], msg.as_string())
    print(f"[preview] sent to {config.email_to}: {subject}")
    print("[preview] nothing written — history, date series and alert state "
          "are untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
