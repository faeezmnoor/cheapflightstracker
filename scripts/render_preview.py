#!/usr/bin/env python3
"""Render the README's screenshot from a real recorded day.

The image in the README is not a mock-up: it is an actual digest, rebuilt by
replaying a day that really ran against the price history in ``data/``. That
matters for the same reason the rest of this project checks output rather than
intent — a hand-drawn screenshot of a tool is a claim about the tool, and this
one can be regenerated and checked.

    python scripts/render_preview.py --date 2026-08-16

Needs Chromium. In CI and in the dev container Playwright's copy is already
present; locally, ``pip install playwright && playwright install chromium``.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import date
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from flightdeals.baseline import load_date_series
from flightdeals.config import Config
from flightdeals.detector import find_deals
from flightdeals.emailer import build_html
from flightdeals.models import RunResult
from flightdeals.search import plan_date_pairs
from replay_audit import load_observations, offers_from_series

OUT = "docs/assets/digest-preview.png"


def find_chromium() -> Optional[str]:
    for pattern in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome",
                    os.path.expanduser(
                        "~/.cache/ms-playwright/chromium-*/chrome-linux/chrome")):
        hits = sorted(glob.glob(pattern))
        if hits:
            return hits[-1]
    return None


def build(run_date: str) -> str:
    config = Config.from_env()
    observations = load_observations("data/price_history.json")
    series = load_date_series("data/date_prices.json")
    prior = [o for o in observations
             if (o.get("observed_date") or "") < run_date]
    offers = offers_from_series(series, run_date)
    by_route: dict = {}
    for offer in offers:
        by_route.setdefault(offer.route_key, []).append(offer)

    as_date = date.fromisoformat(run_date)
    scanned = sorted({d for d, _ in plan_date_pairs(config, as_date)})
    deals, summaries = find_deals(by_route, prior, config.routes, config,
                                  as_date, series, {},
                                  scanned_departures=scanned)
    print(f"[preview] {run_date}: {len(deals)} alert(s), "
          f"{len(summaries)} routes")
    return build_html(RunResult(run_date, config.currency, deals, summaries,
                                len(offers), [], scanned_departures=scanned))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default="2026-08-16",
                        help="which recorded day to render")
    parser.add_argument("--out", default=OUT)
    parser.add_argument("--height", type=int, default=780)
    args = parser.parse_args(argv)

    html = build(args.date)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    scratch = os.path.join(os.path.dirname(args.out) or ".", "_digest.html")
    with open(scratch, "w", encoding="utf-8") as fh:
        fh.write(html)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[preview] playwright not installed — HTML written to "
              f"{scratch}, screenshot skipped")
        return 0

    binary = find_chromium()
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=binary,
                                    args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 700, "height": 1000},
                                device_scale_factor=2)
        page.goto("file://" + os.path.abspath(scratch))
        page.wait_for_timeout(400)
        page.screenshot(path=args.out,
                        clip={"x": 0, "y": 0, "width": 700,
                              "height": args.height})
        browser.close()
    os.remove(scratch)
    print(f"[preview] wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
