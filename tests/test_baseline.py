import os
import sys
import tempfile
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flightdeals.baseline import (append_observations, compute_baseline,
                                  load_history, prune_history, save_history)
from flightdeals.models import Offer


def _offer(dest, price, dep="2026-09-01"):
    return Offer(origin="KUL", destination=dest, departure_date=dep,
                 price=price, currency="MYR", trip_type="one_way")


class BaselineTest(unittest.TestCase):
    def _records(self, prices, route_dest="CGK", observed=None):
        """One price per day by default, since baselines are built from the
        cheapest fare seen on each day."""
        recs = []
        for i, p in enumerate(prices):
            o = _offer(route_dest, p)
            r = o.to_record()
            r["observed_date"] = (
                observed or (date(2026, 7, 1) + timedelta(days=i)).isoformat()
            )
            recs.append(r)
        return recs

    def test_empty_history_gives_no_baseline(self):
        b = compute_baseline([], "KUL-CGK", "one_way", 90, date(2026, 8, 1))
        self.assertEqual(b.samples, 0)
        self.assertFalse(b.is_reliable)

    def test_median_and_percentile(self):
        recs = self._records([100, 200, 300, 400, 500])
        b = compute_baseline(recs, "KUL-CGK", "one_way", 90, date(2026, 8, 2))
        self.assertEqual(b.samples, 5)
        self.assertEqual(b.median, 300)
        self.assertEqual(b.minimum, 100)
        self.assertEqual(b.maximum, 500)
        self.assertEqual(b.p25, 200)  # linear-interp p25 of 1..5 evenly spaced

    def test_window_excludes_old_records(self):
        today = date(2026, 8, 1)
        old = (today - timedelta(days=200)).isoformat()
        recs = self._records([100, 100], observed=old)
        recs += self._records([500], observed=today.isoformat())
        b = compute_baseline(recs, "KUL-CGK", "one_way", 90, today)
        self.assertEqual(b.samples, 1)
        self.assertEqual(b.median, 500)

    def test_route_isolation(self):
        recs = self._records([100], route_dest="CGK")
        recs += self._records([900], route_dest="DPS")
        b = compute_baseline(recs, "KUL-DPS", "one_way", 90, date(2026, 8, 2))
        self.assertEqual(b.samples, 1)
        self.assertEqual(b.median, 900)

    def test_one_way_and_round_trip_baselines_are_separate(self):
        """Regression: pooling trip types put the median between them, so
        every one-way looked ~50% underpriced and fired false SEVERE alerts."""
        recs = []
        for i, (price, trip) in enumerate([(300, "one_way"), (300, "one_way"),
                                           (300, "one_way")]):
            o = _offer("CGK", price)
            r = o.to_record()
            r["trip_type"] = trip
            r["observed_date"] = (date(2026, 7, 1) + timedelta(days=i)).isoformat()
            recs.append(r)
        for i, (price, trip) in enumerate([(600, "round_trip"), (600, "round_trip"),
                                           (600, "round_trip")]):
            o = _offer("CGK", price)
            r = o.to_record()
            r["trip_type"] = trip
            r["observed_date"] = (date(2026, 7, 1) + timedelta(days=i)).isoformat()
            recs.append(r)

        ow = compute_baseline(recs, "KUL-CGK", "one_way", 90, date(2026, 8, 2))
        rt = compute_baseline(recs, "KUL-CGK", "round_trip", 90, date(2026, 8, 2))
        self.assertEqual((ow.samples, ow.median), (3, 300))
        self.assertEqual((rt.samples, rt.median), (3, 600))
        # A normal 300 one-way must not read as a discount off a pooled 450.
        self.assertEqual(ow.median, 300)

    def test_records_without_trip_type_count_as_one_way(self):
        recs = self._records([200, 200])
        for r in recs:
            r.pop("trip_type", None)
        b = compute_baseline(recs, "KUL-CGK", "one_way", 90, date(2026, 8, 2))
        self.assertEqual(b.samples, 2)
        rt = compute_baseline(recs, "KUL-CGK", "round_trip", 90, date(2026, 8, 2))
        self.assertEqual(rt.samples, 0)

    def test_prune_drops_old(self):
        today = date(2026, 8, 1)
        recs = self._records([1], observed=(today - timedelta(days=400)).isoformat())
        recs += self._records([2], observed=today.isoformat())
        kept = prune_history(recs, 120, today)
        self.assertEqual(len(kept), 1)

    def test_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "sub", "history.json")
            recs = append_observations([], [_offer("CGK", 250)], "2026-08-01")
            save_history(path, recs)
            self.assertTrue(os.path.exists(path))
            loaded = load_history(path)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0]["price"], 250)

    def test_load_missing_file(self):
        self.assertEqual(load_history("/nonexistent/path/x.json"), [])


if __name__ == "__main__":
    unittest.main()
