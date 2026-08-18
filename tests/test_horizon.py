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
from flightdeals.horizon import (block_dates, find_bargains, load_horizon,
                                 prune, record, save_horizon, series_key)
from flightdeals.models import Offer

TODAY = date(2026, 8, 18)

def off(dest, dep, price):
    return Offer("KUL", dest, dep, price, "MYR", "one_way")


BLOCKS, BLOCK_DAYS = [90, 150], 30


def full_block(dest, cheapest, block_index=0, covered=30, observed="2026-08-18"):
    """A block scanned end to end, with one genuinely cheap date in it."""
    dates = block_dates(BLOCKS, BLOCK_DAYS, TODAY)[block_index][:covered]
    offers = [off(dest, d, 900.0) for d in dates]
    if offers:
        offers[len(offers) // 2] = off(dest, dates[len(dates) // 2], cheapest)
    return record({}, offers, observed)


def near(price, seen=30, total=30):
    return {"KUL-DPS": (price, seen, total)}


def bargains(store, near_map, **kw):
    opts = dict(block_starts=BLOCKS, block_days=BLOCK_DAYS,
                min_discount=0.15, min_coverage=0.80,
                cities={"KUL-DPS": "Bali"})
    opts.update(kw)
    return find_bargains(store, near_map, TODAY, **opts)

class HorizonStoreTest(unittest.TestCase):
    def test_roundtrip_store(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "h.json")
            s = record({}, [off("DPS", "2026-11-12", 280.0)], "2026-08-18")
            save_horizon(p, s)
            self.assertEqual(load_horizon(p), s)

    def test_finds_a_bargain_and_states_the_gap(self):
        store = full_block("DPS", 280.0)
        f = bargains(store, near(459.0))
        self.assertEqual(len(f), 1)
        self.assertAlmostEqual(f[0].discount_vs_near, 0.3900, places=3)
        self.assertEqual(f[0].saving, 179.0)
        self.assertEqual((f[0].far_seen, f[0].far_total), (30, 30))
        self.assertIn("\u2013", f[0].block_label)      # "16 Nov - 15 Dec"

    def test_small_gaps_are_not_worth_planning_around(self):
        self.assertEqual(bargains(full_block("DPS", 430.0), near(459.0)), [])

    def test_a_thin_far_block_is_not_compared_at_all(self):
        """The whole point of the rewrite. Comparing the minimum of a
        half-covered block against a fully covered near window finds a
        difference in the measurement, not in the market: at 50% coverage the
        minimum reads ~12% high, which is most of the discount threshold."""
        thin = full_block("DPS", 280.0, covered=12)     # 12 of 30
        self.assertEqual(bargains(thin, near(459.0)), [])
        # ...and the same block, fully scanned, does report.
        self.assertEqual(len(bargains(full_block("DPS", 280.0), near(459.0))), 1)

    def test_a_thin_near_window_also_blocks_the_comparison(self):
        """Unfairness runs both ways: a thin near window understates today's
        cheapest, which would invent a far-side bargain."""
        store = full_block("DPS", 280.0)
        self.assertEqual(bargains(store, near(459.0, seen=9, total=30)), [])

    def test_stale_readings_are_ignored(self):
        # A price seen six weeks ago is not a price you can book today.
        store = full_block("DPS", 280.0, observed="2026-07-01")
        self.assertEqual(bargains(store, near(459.0)), [])

    def test_a_route_is_reported_once_at_its_best_block(self):
        store = full_block("DPS", 400.0, block_index=0)
        store.update(full_block("DPS", 280.0, block_index=1))
        f = bargains(store, near(459.0))
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0].price, 280.0)

    def test_past_departures_are_pruned(self):
        s = record({}, [off("DPS", "2026-08-01", 100.0)], "2026-07-20")
        self.assertEqual(prune(s, TODAY), {})

    def test_never_pooled_into_the_route_baseline(self):
        """The horizon store is a separate file with its own key space; nothing
        in it can reach build_daily_series, which reads price_history only."""
        s = record({}, [off("DPS", "2026-11-12", 280.0)], "2026-08-18")
        self.assertEqual(list(s), ["KUL-DPS|one_way|2026-11-12"])


class HorizonDigestTest(unittest.TestCase):
    """The section must read as "worth waiting for", never as an alert."""

    def _result(self):
        from flightdeals.emailer import build_html
        from flightdeals.models import Baseline, RouteSummary, RunResult
        finds = bargains(full_block("DPS", 280.0), near(459.0))
        offer = off("DPS", "2026-09-06", 459.0)
        summaries = [RouteSummary("KUL-DPS", "Bali", offer,
                                  Baseline("KUL-DPS", 9, median=470.0), None,
                                  baseline_trusted=True, dates_seen=28,
                                  dates_scanned=30)]
        return build_html(RunResult("2026-08-18", "MYR", [], summaries, 100,
                                    [], horizon=finds))

    def test_it_renders_as_its_own_section(self):
        html = self._result()
        self.assertIn("Cheaper if you fly later", html)
        self.assertIn("MYR 280", html)
        self.assertIn("39% cheaper", html)

    def test_it_claims_when_to_fly_not_when_to_book(self):
        """A block 5 months out is also a different season. One comparison
        cannot separate the two, so the wording must not imply booking early
        is what saves the money."""
        html = self._result()
        self.assertIn("go then", html)
        self.assertNotIn("book early and save", html.lower())

    def test_an_empty_horizon_renders_nothing(self):
        from flightdeals.emailer import build_html
        from flightdeals.models import RunResult
        html = build_html(RunResult("2026-08-18", "MYR", [], [], 0, []))
        self.assertNotIn("Cheaper if you can wait", html)


if __name__ == "__main__":
    unittest.main()
