"""Entry point: run one daily scan end-to-end.

    load config -> search all routes/dates -> compute baselines from prior
    history -> flag deals -> email digest -> append today's observations and
    persist history.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone

from .baseline import (append_observations, load_history, prune_history,
                       save_history)
from .config import Config
from .detector import find_deals
from .emailer import send_email
from .models import RunResult
from .providers import get_provider
from .search import run_searches


def run(config: Config, today: date | None = None) -> RunResult:
    today = today or datetime.now(timezone.utc).date()
    print(f"[scan] {today.isoformat()} | provider={config.provider} | "
          f"routes={len(config.routes)} | currency={config.currency}")

    provider = get_provider(config)
    offers_by_route, errors = run_searches(provider, config, today)
    offers_checked = sum(len(v) for v in offers_by_route.values())
    print(f"[scan] collected {offers_checked} offers, {len(errors)} error(s)")

    # Baseline must reflect the PRIOR history, so load & evaluate before appending.
    history = load_history(config.history_path)
    deals, summaries = find_deals(
        offers_by_route, history, config.routes, config, today
    )
    print(f"[scan] flagged {len(deals)} deal(s)")

    result = RunResult(
        run_date=today.isoformat(),
        currency=config.currency,
        deals=deals,
        summaries=summaries,
        offers_checked=offers_checked,
        errors=errors,
    )

    send_email(result, config)

    # Record today's observations for tomorrow's baseline, then persist.
    all_offers = [o for offers in offers_by_route.values() for o in offers]
    history = append_observations(history, all_offers, today.isoformat())
    history = prune_history(history, config.history_window_days + 30, today)
    save_history(config.history_path, history)
    print(f"[scan] history now holds {len(history)} observations "
          f"-> {config.history_path}")

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Daily KL->Indonesia flight-deal scan")
    parser.add_argument("--provider", help="Override PROVIDER (googleflights|mock)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the email instead of sending it")
    parser.add_argument("--date", help="Override 'today' as YYYY-MM-DD (testing)")
    args = parser.parse_args(argv)

    config = Config.from_env()
    if args.provider:
        config.provider = args.provider
    if args.dry_run:
        config.dry_run = True

    today = None
    if args.date:
        today = datetime.strptime(args.date, "%Y-%m-%d").date()

    try:
        run(config, today)
    except Exception as exc:  # noqa: BLE001
        print(f"[fatal] {exc!r}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
