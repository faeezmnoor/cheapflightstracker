"""Serialise a run into the flat record the QA auditor reads.

The auditor deliberately knows nothing about ``RunResult``, ``Deal`` or the
HTML template — it reads this payload and the raw price history, and re-derives
the numbers itself. Keeping the hand-off explicit means the checker cannot
accidentally start trusting the objects it is supposed to be checking.

Anything the digest *claims* belongs here. If a future change makes the email
assert something new, add it to the payload so QA can disagree with it.
"""

from __future__ import annotations

import json
import os
from typing import Optional

from .config import Config
from .models import RunResult


def digest_payload(result: RunResult, config: Optional[Config] = None) -> dict:
    """Everything the email asserts, as plain JSON-able data."""
    return {
        "run_date": result.run_date,
        "currency": result.currency,
        "offers_checked": result.offers_checked,
        "scanned_departures": list(result.scanned_departures or []),
        "errors": list(result.errors or []),
        # Thresholds travel with the payload so the auditor judges the run by
        # the settings it actually ran under, not by today's defaults.
        "min_samples": getattr(config, "min_samples", None),
        "departure_window_days": getattr(config, "departure_window_days", None),
        "deals": [
            {
                "route_key": d.offer.route_key,
                "city": d.city,
                "price": d.offer.price,
                "currency": d.offer.currency,
                "trip_type": d.offer.trip_type,
                "departure_date": d.offer.departure_date,
                "return_date": d.offer.return_date,
                "severity": d.severity,
                "basis": d.basis,
                "discount_pct": d.discount_pct,
                "saving": d.saving,
                "median": d.baseline.median,
                "samples": d.baseline.samples,
                "baseline_trip_type": d.baseline.trip_type,
                "z_score": d.z_score,
                "percentile": d.percentile,
                "is_new_low": d.is_new_low,
                "maps_url": d.maps_url,
            }
            for d in result.deals
        ],
        "summaries": [
            {
                "route_key": s.route_key,
                "city": s.city,
                "price": s.cheapest.price if s.cheapest else None,
                "currency": s.cheapest.currency if s.cheapest else None,
                "trip_type": s.cheapest.trip_type if s.cheapest else None,
                "departure_date": s.cheapest.departure_date if s.cheapest else None,
                "median": s.baseline.median if s.baseline_trusted else None,
                "samples": s.baseline.samples,
                "baseline_trusted": s.baseline_trusted,
                "discount_pct": s.discount_pct,
                "maps_url": s.maps_url,
                # How much of the window this route actually returned, so the
                # auditor can tell a minimum from the smallest of three samples.
                "dates_seen": s.dates_seen,
                "dates_scanned": s.dates_scanned,
            }
            for s in result.summaries
        ],
    }


def write_digest(path: str, result: RunResult, html: str,
                 config: Optional[Config] = None,
                 qa: Optional[list] = None) -> str:
    """Write ``<path>`` (JSON payload) and ``<path>.html`` beside it.

    Both are CI artifacts: when a digest looks wrong, the pair is the evidence
    needed to reproduce the decision offline, without re-scraping anything.

    Deliberately captures the digest **as judged**, before any suppression —
    the interesting question after a bad morning is what was rejected and why,
    and a payload with the evidence already removed cannot answer it. The
    ``qa`` block records the verdict alongside it, so re-auditing this file
    reproduces the original decision rather than the cleaned-up one.
    """
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    payload = digest_payload(result, config)
    if qa is not None:
        payload["qa"] = [
            {"check": f.check, "severity": f.severity, "message": f.message,
             "evidence": f.evidence, "route_key": f.route_key}
            for f in qa
        ]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
    html_path = os.path.splitext(path)[0] + ".html"
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return html_path
