"""The far-horizon lane — fares 45-180 days out, sampled weekly.

Its whole reason to exist is that the 30-day window sits on the wrong part of
the booking curve: measured on our own history, fares inside 5 days run ~8%
above a route's median while fares 21-25 days out run ~6% below, and the curve
has not bottomed where we stop looking. Southeast Asia is repeatedly found to
bottom at 3-6 months, and AirAsia's sale campaigns sell travel 6-12 months out.

The tests below guard the separation, which is the part that can quietly break:
horizon prices must never reach the route baselines, and a fare nobody has
re-checked in weeks must not be presented as bookable.
"""

import os, sys, unittest, tempfile
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from flightdeals.horizon import (find_bargains, load_horizon, prune, record,
                                 save_horizon, series_key)
from flightdeals.models import Offer

TODAY = date(2026, 8, 18)

def off(dest, dep, price):
    return Offer("KUL", dest, dep, price, "MYR", "one_way")

class HorizonStoreTest(unittest.TestCase):
    def test_roundtrip_store(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "h.json")
            s = record({}, [off("DPS", "2026-11-12", 280.0)], "2026-08-18")
            save_horizon(p, s)
            self.assertEqual(load_horizon(p), s)

    def test_finds_a_bargain_and_states_the_gap(self):
        s = record({}, [off("DPS", "2026-11-12", 280.0)], "2026-08-18")
        f = find_bargains(s, {"KUL-DPS": 459.0}, TODAY, 0.15,
                          cities={"KUL-DPS": "Bali"})
        self.assertEqual(len(f), 1)
        self.assertAlmostEqual(f[0].discount_vs_near, 0.3900, places=3)
        self.assertEqual(f[0].days_ahead, 86)
        self.assertEqual(f[0].saving, 179.0)

    def test_small_gaps_are_not_worth_planning_around(self):
        s = record({}, [off("DPS", "2026-11-12", 430.0)], "2026-08-18")
        self.assertEqual(find_bargains(s, {"KUL-DPS": 459.0}, TODAY, 0.15), [])

    def test_stale_readings_are_ignored(self):
        # A price seen 40 days ago is not a price you can book today.
        s = record({}, [off("DPS", "2026-11-12", 280.0)], "2026-07-09")
        self.assertEqual(find_bargains(s, {"KUL-DPS": 459.0}, TODAY, 0.15), [])

    def test_past_departures_are_pruned(self):
        s = record({}, [off("DPS", "2026-08-01", 100.0)], "2026-07-20")
        self.assertEqual(prune(s, TODAY), {})

    def test_never_pooled_into_the_route_baseline(self):
        """The horizon store is a separate file with its own key space; nothing
        in it can reach build_daily_series, which reads price_history only."""
        s = record({}, [off("DPS", "2026-11-12", 280.0)], "2026-08-18")
        self.assertEqual(list(s), ["KUL-DPS|one_way|2026-11-12"])
        self.assertNotIn("observed_date", str(s))



class HorizonDigestTest(unittest.TestCase):
    """The section must read as "worth waiting for", never as an alert."""

    def _result(self):
        from flightdeals.emailer import build_html
        from flightdeals.horizon import find_bargains, record
        from flightdeals.models import Baseline, RouteSummary, RunResult
        store = record({}, [off("DPS", "2026-11-12", 280.0)], "2026-08-18")
        finds = find_bargains(store, {"KUL-DPS": 459.0}, TODAY, 0.15,
                              cities={"KUL-DPS": "Bali"})
        offer = off("DPS", "2026-09-06", 459.0)
        summaries = [RouteSummary("KUL-DPS", "Bali", offer,
                                  Baseline("KUL-DPS", 9, median=470.0), None,
                                  baseline_trusted=True, dates_seen=28,
                                  dates_scanned=30)]
        return build_html(RunResult("2026-08-18", "MYR", [], summaries, 100,
                                    [], horizon=finds))

    def test_it_renders_as_its_own_section(self):
        html = self._result()
        self.assertIn("Cheaper if you can wait", html)
        self.assertIn("MYR 280", html)
        self.assertIn("86d out", html)

    def test_it_never_claims_to_be_a_full_scan(self):
        """The near window earns the word "cheapest" by covering every date.
        This lane samples, and must say so rather than borrow the claim."""
        html = self._result()
        self.assertIn("not a full scan", html)

    def test_an_empty_horizon_renders_nothing(self):
        from flightdeals.emailer import build_html
        from flightdeals.models import RunResult
        html = build_html(RunResult("2026-08-18", "MYR", [], [], 0, []))
        self.assertNotIn("Cheaper if you can wait", html)


if __name__ == "__main__":
    unittest.main()
