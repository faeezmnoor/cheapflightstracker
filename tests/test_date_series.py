import os
import sys
import tempfile
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flightdeals.baseline import (date_baseline, load_alert_state,
                                  load_date_series, prune_date_series,
                                  record_date_prices, save_alert_state,
                                  save_date_series, series_key, should_repeat)
from flightdeals.config import Config, Route
from flightdeals.detector import find_deals
from flightdeals.models import Offer


def _cfg(**kw):
    c = Config(min_samples=5, history_window_days=90)
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def _route_history(dest, prices, start=date(2026, 8, 1), dep="2026-09-08"):
    """One daily-cheapest record per day."""
    return [{
        "origin": "KUL", "destination": dest, "departure_date": dep,
        "price": p, "currency": "MYR", "trip_type": "one_way",
        "observed_date": (start + timedelta(days=i)).isoformat(),
    } for i, p in enumerate(prices)]


def _offer(dest, price, dep="2026-09-08"):
    return Offer("KUL", dest, dep, price, "MYR", "one_way")


class DateSeriesStoreTest(unittest.TestCase):
    def test_record_and_read_back(self):
        series = record_date_prices({}, [_offer("UPG", 608)], "2026-08-09")
        series = record_date_prices(series, [_offer("UPG", 469)], "2026-08-10")
        key = series_key("KUL-UPG", "one_way", "2026-09-08")
        self.assertEqual(series[key], {"2026-08-09": 608.0, "2026-08-10": 469.0})

    def test_keeps_cheapest_within_a_day(self):
        series = record_date_prices({}, [_offer("UPG", 700), _offer("UPG", 480)],
                                    "2026-08-10")
        self.assertEqual(series[series_key("KUL-UPG", "one_way", "2026-09-08")],
                         {"2026-08-10": 480.0})

    def test_baseline_excludes_today(self):
        series = record_date_prices({}, [_offer("UPG", 608)], "2026-08-09")
        series = record_date_prices(series, [_offer("UPG", 469)], "2026-08-10")
        median, samples, prev, prev_date = date_baseline(
            series, "KUL-UPG", "one_way", "2026-09-08", date(2026, 8, 10))
        self.assertEqual((median, samples), (608.0, 1))
        self.assertEqual((prev, prev_date), (608.0, "2026-08-09"))

    def test_prune_drops_past_departures(self):
        series = record_date_prices({}, [_offer("UPG", 500, dep="2026-08-01")],
                                    "2026-07-30")
        series = record_date_prices(series, [_offer("UPG", 500)], "2026-08-10")
        pruned = prune_date_series(series, date(2026, 8, 10))
        self.assertEqual(list(pruned),
                         [series_key("KUL-UPG", "one_way", "2026-09-08")])

    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "sub", "dates.json")
            series = record_date_prices({}, [_offer("UPG", 469)], "2026-08-10")
            save_date_series(p, series)
            self.assertEqual(load_date_series(p), series)

    def test_load_missing_file(self):
        self.assertEqual(load_date_series("/nonexistent/x.json"), {})


class NoisyDateReadingsTest(unittest.TestCase):
    """The live failure: a scrape that misses the cheap itineraries records a
    wildly high price for one date. Judging the next day's fare against that
    single reading produced an '85% off' alert for KL->Batam, on a route whose
    fare had been 279 all week."""

    def setUp(self):
        self.route = Route("KUL", "BTH", "Batam")
        self.today = date(2026, 8, 12)
        self.history = _route_history("BTH", [279, 279, 285, 279, 279, 279])

    def test_a_junk_prior_reading_cannot_manufacture_an_alert(self):
        # 11 Aug recorded 2,110 for 31 Aug — an artifact, not a price.
        series = record_date_prices({}, [_offer("BTH", 2110, dep="2026-08-31")],
                                    "2026-08-11")
        # Today that date is 309, while the route's genuine cheapest is 279.
        offers = {"KUL-BTH": [_offer("BTH", 279, dep="2026-08-13"),
                              _offer("BTH", 309, dep="2026-08-31")]}
        deals, summaries = find_deals(offers, self.history, [self.route],
                                      _cfg(), self.today, series)
        self.assertEqual(deals, [],
                         "a junk prior reading must not become a baseline")
        # And the digest still shows the genuinely cheapest fare.
        self.assertEqual(summaries[0].cheapest.price, 279)

    def test_alert_is_always_the_fare_the_digest_shows(self):
        """The alert quoted 309 while the table showed 279 available."""
        history = _route_history("BTH", [500, 505, 495, 500, 500, 500])
        offers = {"KUL-BTH": [_offer("BTH", 279, dep="2026-08-13"),
                              _offer("BTH", 309, dep="2026-08-31")]}
        deals, summaries = find_deals(offers, history, [self.route], _cfg(),
                                      self.today, {})
        self.assertEqual(len(deals), 1)
        self.assertEqual(deals[0].offer.price, summaries[0].cheapest.price)
        self.assertEqual(deals[0].offer.price, 279)


class RepeatSuppressionTest(unittest.TestCase):
    """A fare that stays cheap stays statistically unusual. Without explicit
    state it would be re-sent every morning until the median caught up."""

    def setUp(self):
        self.route = Route("KUL", "UPG", "Makassar")
        self.history = _route_history("UPG", [608, 608, 610, 608, 605, 608])

    def test_same_fare_is_not_repeated(self):
        offers = {"KUL-UPG": [_offer("UPG", 469)]}
        deals, _ = find_deals(offers, self.history, [self.route], _cfg(),
                              date(2026, 8, 12), {}, last_alerts={})
        self.assertEqual(len(deals), 1)

        already = {"KUL-UPG": {"price": 469, "date": "2026-08-12",
                               "departure_date": "2026-09-08"}}
        deals, _ = find_deals(offers, self.history, [self.route], _cfg(),
                              date(2026, 8, 13), {}, last_alerts=already)
        self.assertEqual(deals, [], "an unchanged fare must not be re-sent")

    def test_a_further_drop_is_worth_repeating(self):
        already = {"KUL-UPG": {"price": 469, "date": "2026-08-12",
                               "departure_date": "2026-09-08"}}
        deals, _ = find_deals({"KUL-UPG": [_offer("UPG", 400)]}, self.history,
                              [self.route], _cfg(), date(2026, 8, 13), {},
                              last_alerts=already)
        self.assertEqual(len(deals), 1)

    def test_reminder_after_the_cooldown(self):
        already = {"KUL-UPG": {"price": 469, "date": "2026-08-01",
                               "departure_date": "2026-09-08"}}
        deals, _ = find_deals({"KUL-UPG": [_offer("UPG", 469)]}, self.history,
                              [self.route], _cfg(repeat_cooldown_days=7),
                              date(2026, 8, 12), {}, last_alerts=already)
        self.assertEqual(len(deals), 1)

    def test_should_repeat_rules(self):
        prev = {"price": 500, "date": "2026-08-10"}
        self.assertTrue(should_repeat(None, 500, date(2026, 8, 11), 0.05, 7))
        self.assertTrue(should_repeat(prev, 400, date(2026, 8, 11), 0.05, 7))
        self.assertFalse(should_repeat(prev, 495, date(2026, 8, 11), 0.05, 7))
        self.assertTrue(should_repeat(prev, 495, date(2026, 8, 20), 0.05, 7))

    def test_alert_state_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "sub", "alerts.json")
            state = {"KUL-UPG": {"price": 469.0, "date": "2026-08-12"}}
            save_alert_state(p, state)
            self.assertEqual(load_alert_state(p), state)
        self.assertEqual(load_alert_state("/nonexistent/a.json"), {})


if __name__ == "__main__":
    unittest.main()
