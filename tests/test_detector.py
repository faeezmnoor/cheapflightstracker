import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flightdeals.config import Config, Route
from flightdeals.detector import find_deals
from flightdeals.models import Offer


def _cfg(**kw):
    c = Config()
    c.deal_threshold = 0.20
    c.severe_threshold = 0.35
    c.min_samples = 5
    c.history_window_days = 90
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def _history(dest, prices, observed=None):
    """Baselines are built from the cheapest fare per day, so give each price
    its own observation date unless a specific one is requested."""
    recs = []
    for i, p in enumerate(prices):
        recs.append({
            "origin": "KUL", "destination": dest, "departure_date": "2026-09-01",
            "price": p, "currency": "MYR", "trip_type": "one_way",
            "observed_date": (observed
                              or (date(2026, 7, 1) + timedelta(days=i)).isoformat()),
        })
    return recs


def _offer(dest, price):
    return Offer(origin="KUL", destination=dest, departure_date="2026-09-10",
                 price=price, currency="MYR", trip_type="one_way")


class DetectorTest(unittest.TestCase):
    def setUp(self):
        self.route = Route("KUL", "CGK", "Jakarta")
        self.today = date(2026, 8, 2)

    def test_no_deal_when_price_is_normal(self):
        hist = _history("CGK", [300, 300, 300, 300, 300])
        offers = {"KUL-CGK": [_offer("CGK", 290)]}
        deals, summaries = find_deals(offers, hist, [self.route], _cfg(), self.today)
        self.assertEqual(deals, [])
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0].cheapest.price, 290)

    def test_flags_a_deal(self):
        """27% off AND an all-time low grades severe: rare and large is the
        definition, and both halves are satisfied here."""
        hist = _history("CGK", [300, 300, 300, 300, 300])
        offers = {"KUL-CGK": [_offer("CGK", 220)]}  # ~27% off, new low
        deals, _ = find_deals(offers, hist, [self.route], _cfg(), self.today)
        self.assertEqual(len(deals), 1)
        self.assertEqual(deals[0].severity, "severe")
        self.assertTrue(deals[0].is_new_low)
        self.assertAlmostEqual(deals[0].discount_pct, (300 - 220) / 300, places=3)
        self.assertEqual(deals[0].saving, 80)

    def test_moderate_discount_is_a_deal_not_severe(self):
        """Large enough to be worth sending, not rare enough to shout about."""
        hist = _history("CGK", [300, 300, 260, 300, 300])   # 260 already seen
        offers = {"KUL-CGK": [_offer("CGK", 255)]}          # ~15% off
        deals, _ = find_deals(offers, hist, [self.route], _cfg(), self.today)
        self.assertEqual(len(deals), 1)
        self.assertEqual(deals[0].severity, "deal")

    def test_trivial_dip_is_not_worth_an_email(self):
        """Floors: a few ringgit off a steady fare scores an extreme z-score
        but is not news."""
        hist = _history("CGK", [300, 300, 300, 300, 300])
        offers = {"KUL-CGK": [_offer("CGK", 285)]}   # 5% off, saving 15
        deals, _ = find_deals(offers, hist, [self.route], _cfg(), self.today)
        self.assertEqual(deals, [])

    def test_flags_severe(self):
        hist = _history("CGK", [400, 400, 400, 400, 400])
        offers = {"KUL-CGK": [_offer("CGK", 200)]}  # 50% off
        deals, _ = find_deals(offers, hist, [self.route], _cfg(), self.today)
        self.assertEqual(len(deals), 1)
        self.assertEqual(deals[0].severity, "severe")

    def test_thin_history_never_flags(self):
        hist = _history("CGK", [300, 300])  # only 2 < min_samples
        offers = {"KUL-CGK": [_offer("CGK", 50)]}
        deals, summaries = find_deals(offers, hist, [self.route], _cfg(), self.today)
        self.assertEqual(deals, [])
        # baseline not reliable enough -> no discount reported in summary
        self.assertIsNone(summaries[0].discount_pct)

    def test_one_deal_per_route(self):
        hist = _history("CGK", [300, 300, 300, 300, 300])
        offers = {"KUL-CGK": [_offer("CGK", 100), _offer("CGK", 150)]}
        deals, _ = find_deals(offers, hist, [self.route], _cfg(), self.today)
        self.assertEqual(len(deals), 1)
        self.assertEqual(deals[0].offer.price, 100)  # cheapest wins

    def test_no_offers_route_summary(self):
        hist = _history("CGK", [300, 300, 300, 300, 300])
        deals, summaries = find_deals({"KUL-CGK": []}, hist, [self.route], _cfg(), self.today)
        self.assertEqual(deals, [])
        self.assertIsNone(summaries[0].cheapest)

    def test_round_trip_history_does_not_make_one_ways_look_cheap(self):
        """Regression from the first live run: history holds both one-way and
        round-trip fares. Pooling them put 'usual' between the two, so ordinary
        one-ways were reported as ~45% off and flagged SEVERE every day."""
        hist = _history("CGK", [340, 350, 342, 338, 345])            # one-way
        rt = _history("CGK", [900, 920, 890, 910, 905])              # round-trip
        for r in rt:
            r["trip_type"] = "round_trip"
        hist += rt

        # A perfectly ordinary one-way fare.
        offers = {"KUL-CGK": [_offer("CGK", 342)]}
        deals, summaries = find_deals(offers, hist, [self.route], _cfg(), self.today)
        self.assertEqual(deals, [], "ordinary one-way must not be flagged")
        # Baseline used is the one-way one (~342), not a pooled ~600.
        self.assertEqual(summaries[0].baseline.trip_type, "one_way")
        self.assertLess(summaries[0].baseline.median, 400)

    def test_round_trip_offer_uses_round_trip_baseline(self):
        hist = _history("CGK", [340, 350, 342, 338, 345])
        rt = _history("CGK", [900, 920, 890, 910, 905])
        for r in rt:
            r["trip_type"] = "round_trip"
        hist += rt

        cheap_rt = Offer(origin="KUL", destination="CGK",
                         departure_date="2026-09-10", return_date="2026-09-24",
                         price=500, currency="MYR", trip_type="round_trip")
        deals, _ = find_deals({"KUL-CGK": [cheap_rt]}, hist, [self.route],
                              _cfg(), self.today)
        self.assertEqual(len(deals), 1)
        self.assertEqual(deals[0].baseline.trip_type, "round_trip")
        self.assertEqual(deals[0].baseline.median, 905)
        self.assertEqual(deals[0].severity, "severe")   # 500 vs 905 usual

    def test_deal_carries_city_name(self):
        """The digest headlines the city, not the IATA code: an alert reading
        'KL -> UPG' next to a table row saying 'KL -> Makassar' is the same
        route twice in two languages."""
        hist = _history("CGK", [300, 300, 300, 300, 300])
        deals, _ = find_deals({"KUL-CGK": [_offer("CGK", 200)]}, hist,
                              [self.route], _cfg(), self.today)
        self.assertEqual(deals[0].city, "Jakarta")

    def test_summary_marks_untrusted_baselines(self):
        """A 'usual' price must not be shown for a baseline too thin to derive
        a discount from — that reads as 'we know the usual but won't say the
        saving'."""
        thin = _history("CGK", [300, 300])          # 2 days < min_samples 5
        _, summaries = find_deals({"KUL-CGK": [_offer("CGK", 290)]}, thin,
                                  [self.route], _cfg(), self.today)
        self.assertFalse(summaries[0].baseline_trusted)

        mature = _history("CGK", [300] * 5)
        _, summaries = find_deals({"KUL-CGK": [_offer("CGK", 290)]}, mature,
                                  [self.route], _cfg(), self.today)
        self.assertTrue(summaries[0].baseline_trusted)

    def test_deals_sorted_by_discount(self):
        routes = [Route("KUL", "CGK", "Jakarta"), Route("KUL", "DPS", "Bali")]
        hist = _history("CGK", [300] * 5) + _history("DPS", [400] * 5)
        offers = {
            "KUL-CGK": [_offer("CGK", 230)],   # ~23% off
            "KUL-DPS": [_offer("DPS", 200)],   # 50% off
        }
        deals, _ = find_deals(offers, hist, routes, _cfg(), self.today)
        self.assertEqual(len(deals), 2)
        self.assertGreater(deals[0].discount_pct, deals[1].discount_pct)
        self.assertEqual(deals[0].offer.destination, "DPS")


class StalePriceLevelTest(unittest.TestCase):
    """A price that stepped down days ago and held is not news today.

    Real incident, KL->Makassar: the fare fell 960 -> 774 -> 608 -> 469 and
    then sat at exactly 469 for four consecutive days. Because the median still
    reflected the old 608 level, every one of those four days scored "23% off,
    save MYR 139" — announcing a week-old price change as today's opportunity.
    The email gave itself away in its own supporting text: "only 38% of tracked
    days were this cheap".

    A discount must therefore also be *rare* to qualify. The genuine alert on
    the day it actually dropped is a new low and must survive.
    """

    route = Route("KUL", "UPG", "Makassar")
    today = date(2026, 8, 13)

    def _run(self, prices, price_today):
        hist = _history("UPG", prices)
        return find_deals({"KUL-UPG": [_offer("UPG", price_today)]}, hist,
                          [self.route], _cfg(), self.today)[0]

    def test_the_day_it_drops_still_alerts(self):
        deals = self._run([960, 774, 608, 608, 608], 469)
        self.assertEqual(len(deals), 1, "a genuine new low must still alert")
        self.assertTrue(deals[0].is_new_low)

    def test_the_same_fare_days_later_does_not(self):
        # 469 is now four of the nine tracked days — the 44th percentile.
        deals = self._run([960, 774, 608, 608, 608, 469, 469, 469], 469)
        self.assertEqual(deals, [],
                         "a fare that has been the going rate for days is not "
                         "underpriced just because the median lags")

    def test_a_deep_discount_still_needs_to_be_rare(self):
        cfg = _cfg()
        # 30% off, comfortably over deal_threshold, but half the tracked days
        # were this cheap or cheaper.
        hist = _history("UPG", [1000, 1000, 1000, 700, 700, 700])
        deals, _ = find_deals({"KUL-UPG": [_offer("UPG", 700)]}, hist,
                              [self.route], cfg, self.today)
        self.assertEqual(deals, [])

    def test_the_guard_can_be_relaxed_by_configuration(self):
        loose = _cfg(deal_percentile_guard=1.0)
        hist = _history("UPG", [960, 774, 608, 608, 608, 469, 469, 469])
        deals, _ = find_deals({"KUL-UPG": [_offer("UPG", 469)]}, hist,
                              [self.route], loose, self.today)
        self.assertEqual(len(deals), 1, "guard must be the only thing blocking")


if __name__ == "__main__":
    unittest.main()
