#!/usr/bin/env python3
"""Probe which Indonesian airports are actually reachable from KL, and how.

Run this on a machine with open internet (e.g. a GitHub Actions runner) to get
evidence instead of guesses: for each candidate airport it reports whether
Google Flights returns anything, the cheapest fare, and the minimum number of
stops — which is what separates a direct route from an international+domestic
connection.

    python scripts/probe_destinations.py            # all candidates
    python scripts/probe_destinations.py CGK DPS    # just these

Writes a machine-readable summary to probe_results.json as well as printing a
table, so the results can be reviewed after the run.
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flightdeals.config import Config              # noqa: E402
from flightdeals.providers.googleflights import (  # noqa: E402
    GoogleFlightsProvider)

# Candidate Indonesian airports, grouped by island. Includes places that need
# a connection — Google returns multi-leg itineraries, so an international
# +domestic hop shows up as an offer with stops >= 1.
CANDIDATES = {
    "Sumatra": {
        "KNO": "Medan", "BTJ": "Banda Aceh", "DTB": "Silangit (Lake Toba)",
        "PDG": "Padang", "PKU": "Pekanbaru", "PLM": "Palembang",
        "DJB": "Jambi", "BKS": "Bengkulu", "TKG": "Bandar Lampung",
        "PGK": "Pangkal Pinang (Bangka)", "TJQ": "Tanjung Pandan (Belitung)",
        "BTH": "Batam", "TNJ": "Tanjung Pinang",
    },
    "Java": {
        "CGK": "Jakarta (Soekarno-Hatta)", "HLP": "Jakarta (Halim)",
        "BDO": "Bandung", "KJT": "Kertajati", "SRG": "Semarang",
        "SOC": "Solo (Surakarta)", "YIA": "Yogyakarta", "SUB": "Surabaya",
        "MLG": "Malang", "BWX": "Banyuwangi",
    },
    "Bali & Nusa Tenggara": {
        "DPS": "Denpasar (Bali)", "LOP": "Lombok",
        "LBJ": "Labuan Bajo (Komodo)", "TMC": "Tambolaka (Sumba)",
        "WGP": "Waingapu (Sumba)", "MOF": "Maumere", "ENE": "Ende",
        "KOE": "Kupang",
    },
    "Kalimantan": {
        "PNK": "Pontianak", "BDJ": "Banjarmasin", "BPN": "Balikpapan",
        "PKY": "Palangkaraya", "TRK": "Tarakan", "BEJ": "Berau (Derawan)",
    },
    "Sulawesi": {
        "UPG": "Makassar", "MDC": "Manado (Bunaken)", "PLW": "Palu",
        "KDI": "Kendari", "GTO": "Gorontalo",
    },
    "Maluku & Papua": {
        "AMQ": "Ambon", "TTE": "Ternate", "SOQ": "Sorong (Raja Ampat)",
        "DJJ": "Jayapura", "TIM": "Timika", "BIK": "Biak",
        "MKW": "Manokwari",
    },
}


def main(argv: list[str]) -> int:
    wanted = {c.upper() for c in argv[1:]}
    flat: list[tuple[str, str, str]] = []
    for island, airports in CANDIDATES.items():
        for code, city in airports.items():
            if not wanted or code in wanted:
                flat.append((island, code, city))

    config = Config.from_env()
    config.provider = "googleflights"
    provider = GoogleFlightsProvider(config)

    today = date.today()
    # Two dates so a one-off blackout doesn't read as "route doesn't exist".
    probe_dates = [(today + timedelta(days=21)).isoformat(),
                   (today + timedelta(days=35)).isoformat()]

    print(f"Probing {len(flat)} airports from {config.origin} "
          f"on {', '.join(probe_dates)} ({config.currency})\n")
    print(f"{'code':<5}{'city':<28}{'offers':>7}{'cheapest':>10}{'stops':>7}  island")
    print("-" * 78)

    results = []
    for island, code, city in flat:
        offers = []
        for dep in probe_dates:
            try:
                offers.extend(provider.search(config.origin, code, dep))
            except Exception as exc:                       # noqa: BLE001
                print(f"{code:<5}{city:<28}{'ERROR':>7}  {exc}"[:110])
            time.sleep(2.0 + random.uniform(0, 1.5))

        if offers:
            cheapest = min(offers, key=lambda o: o.price)
            min_stops = min((o.stops for o in offers if o.stops is not None),
                            default=None)
            print(f"{code:<5}{city:<28}{len(offers):>7}"
                  f"{cheapest.price:>10.0f}{str(min_stops):>7}  {island}")
        else:
            cheapest, min_stops = None, None
            print(f"{code:<5}{city:<28}{0:>7}{'-':>10}{'-':>7}  {island}")

        results.append({
            "island": island, "code": code, "city": city,
            "offers": len(offers),
            "cheapest": cheapest.price if cheapest else None,
            "min_stops": min_stops,
            "airline": cheapest.airline if cheapest else None,
        })

    with open("probe_results.json", "w", encoding="utf-8") as fh:
        json.dump({"origin": config.origin, "currency": config.currency,
                   "dates": probe_dates, "results": results}, fh, indent=2)

    reachable = [r for r in results if r["offers"]]
    direct = [r for r in reachable if r["min_stops"] == 0]
    print("\n" + "=" * 78)
    print(f"reachable: {len(reachable)}/{len(results)}   "
          f"direct: {len(direct)}   connecting-only: "
          f"{len(reachable) - len(direct)}")
    print("direct   :", ", ".join(sorted(r["code"] for r in direct)))
    print("connect  :", ", ".join(sorted(r["code"] for r in reachable
                                         if r["min_stops"] != 0)))
    print("no service:", ", ".join(sorted(r["code"] for r in results
                                          if not r["offers"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
