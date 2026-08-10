import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flightdeals.config import Config, Route
from flightdeals.detector import find_deals
from flightdeals.emailer import build_html, build_subject, build_text
from flightdeals.models import Baseline, Deal, Offer, RouteSummary, RunResult
from flightdeals.providers.mock import MockProvider
from flightdeals.search import plan_date_pairs, run_searches


class SearchPlanTest(unittest.TestCase):
    def test_oneway_only(self):
        c = Config(departure_offsets=[10, 20], round_trip=False)
        pairs = plan_date_pairs(c, date(2026, 8, 1))
        self.assertEqual(pairs, [("2026-08-11", None), ("2026-08-21", None)])

    def test_round_trip_within_window(self):
        # One-ways come from departure_offsets; round trips from their own
        # (smaller) round_trip_offsets, so each extra return date is a
        # deliberate request rather than a multiplier on every date.
        c = Config(departure_offsets=[10], round_trip=True,
                   round_trip_offsets=[10], stay_lengths=[7, 40],
                   max_trip_days=30)
        pairs = plan_date_pairs(c, date(2026, 8, 1))
        self.assertIn(("2026-08-11", None), pairs)
        self.assertIn(("2026-08-11", "2026-08-18"), pairs)
        # a 40-day stay exceeds max_trip_days and is dropped
        self.assertNotIn(("2026-08-11", "2026-09-20"), pairs)

    def test_round_trip_offsets_are_independent_of_one_way_dates(self):
        c = Config(departure_offsets=[10, 20], round_trip=True,
                   round_trip_offsets=[30], stay_lengths=[7], max_trip_days=30)
        pairs = plan_date_pairs(c, date(2026, 8, 1))
        self.assertEqual([p for p in pairs if p[1] is None],
                         [("2026-08-11", None), ("2026-08-21", None)])
        self.assertEqual([p for p in pairs if p[1]],
                         [("2026-08-31", "2026-09-07")])

    def test_pairs_are_ordered_earliest_first(self):
        c = Config(departure_offsets=[30, 10, 20], round_trip=False)
        pairs = plan_date_pairs(c, date(2026, 8, 1))
        self.assertEqual([p[0] for p in pairs],
                         sorted(p[0] for p in pairs))

    def test_run_searches_with_mock(self):
        routes = [Route("KUL", "CGK", "Jakarta")]
        c = Config(routes=routes, provider="mock", round_trip=False,
                   departure_offsets=[14], request_pause_seconds=0.0)
        offers, errors = run_searches(MockProvider(c), c, date(2026, 8, 1))
        self.assertEqual(errors, [])
        self.assertGreater(len(offers["KUL-CGK"]), 0)
        self.assertTrue(all(o.price > 0 for o in offers["KUL-CGK"]))


class EmailTest(unittest.TestCase):
    def _result(self, with_deals=True):
        offer = Offer("KUL", "DPS", "2026-09-01", 200.0, "MYR", "one_way",
                      airline="AK", stops=0,
                      deep_link="https://example.com/x")
        baseline = Baseline("KUL-DPS", 10, median=400.0, mean=410.0,
                            p25=350.0, minimum=200.0, maximum=600.0)
        deals = []
        if with_deals:
            deals = [Deal(offer=offer, baseline=baseline,
                          discount_pct=0.5, saving=200.0, severity="severe")]
        summaries = [RouteSummary("KUL-DPS", "Bali", offer, baseline, 0.5)]
        return RunResult("2026-08-04", "MYR", deals, summaries, 42, [])

    def test_subject_with_deals(self):
        subj = build_subject(self._result(True))
        self.assertIn("DPS", subj)
        self.assertIn("off", subj)

    def test_subject_no_deals(self):
        subj = build_subject(self._result(False))
        self.assertIn("No", subj)

    def test_text_body_contains_key_numbers(self):
        text = build_text(self._result(True))
        self.assertIn("MYR 200", text)
        self.assertIn("DPS", text)
        self.assertIn("SEVERE", text)

    def test_html_is_wellformed_ish(self):
        html = build_html(self._result(True))
        self.assertIn("<html>", html)
        self.assertIn("</html>", html)
        self.assertIn("KL &rarr; DPS", html)
        self.assertIn("SEVERELY UNDERPRICED", html)

    def test_html_handles_no_deals(self):
        html = build_html(self._result(False))
        self.assertIn("No underpriced flights today", html)

    def test_summary_table_labels_trip_type_and_date(self):
        """Regression: the digest table showed a round-trip price in the same
        column as one-way fares with no label, so a return fare read as the
        route simply being twice as expensive."""
        one_way = Offer("KUL", "CGK", "2026-09-09", 342.0, "MYR", "one_way")
        ret = Offer("KUL", "UPG", "2026-09-09", 960.0, "MYR", "round_trip",
                    return_date="2026-09-23")
        b = Baseline("KUL-CGK", 0)
        result = RunResult("2026-08-05", "MYR", [], [
            RouteSummary("KUL-CGK", "Jakarta", one_way, b, None),
            RouteSummary("KUL-UPG", "Makassar", ret, b, None),
        ], 205, [])
        html = build_html(result)
        self.assertIn("9 Sep · one-way", html)
        self.assertIn("9 Sep → 23 Sep · return", html)
        self.assertIn(">When<", html)

    def test_untrusted_baseline_shows_building_not_a_price(self):
        offer = Offer("KUL", "PNK", "2026-08-20", 302.0, "MYR", "one_way")
        b = Baseline("KUL-PNK", 3, median=309.0)      # only 3 days
        result = RunResult("2026-08-10", "MYR", [], [
            RouteSummary("KUL-PNK", "Pontianak", offer, b, None,
                         baseline_trusted=False)], 100, [])
        html = build_html(result)
        self.assertIn("building", html)
        self.assertNotIn("MYR 309", html)

        result.summaries[0].baseline_trusted = True
        html = build_html(result)
        self.assertIn("MYR 309", html)

    def test_deal_card_uses_city_name(self):
        offer = Offer("KUL", "UPG", "2026-09-08", 469.0, "MYR", "one_way",
                      airline="AirAsia", stops=0)
        b = Baseline("KUL-UPG", 5, median=608.0)
        deal = Deal(offer=offer, baseline=b, discount_pct=0.229,
                    saving=139.0, severity="deal", city="Makassar")
        result = RunResult("2026-08-10", "MYR", [deal], [], 3416, [])
        html = build_html(result)
        self.assertIn("KL &rarr; Makassar", html)
        self.assertIn("Makassar", build_subject(result))
        self.assertIn("Makassar", build_text(result))

    def test_no_offers_row_spans_all_columns(self):
        b = Baseline("KUL-JOG", 0)
        result = RunResult("2026-08-05", "MYR", [], [
            RouteSummary("KUL-JOG", "Yogyakarta", None, b, None),
        ], 0, [])
        html = build_html(result)
        # 5 columns now (Route, Cheapest, When, Off usual, Usual)
        self.assertIn('colspan="4"', html)
        self.assertIn("no offers", html)


class EndToEndMockTest(unittest.TestCase):
    def test_full_pipeline_runs(self):
        routes = [Route("KUL", "CGK", "Jakarta"), Route("KUL", "DPS", "Bali")]
        c = Config(routes=routes, provider="mock", round_trip=False,
                   departure_offsets=[14, 30], request_pause_seconds=0.0,
                   min_samples=1)
        today = date(2026, 8, 1)
        offers, _ = run_searches(MockProvider(c), c, today)
        # seed a baseline so detection has something to compare against
        history = []
        for rk, offs in offers.items():
            for o in offs:
                r = o.to_record()
                r["observed_date"] = "2026-07-15"
                r["price"] = 500  # pretend usual was pricey
                history.append(r)
        deals, summaries = find_deals(offers, history, routes, c, today)
        self.assertEqual(len(summaries), 2)
        # with a 500 baseline and mock fares well under that, expect deals
        self.assertGreater(len(deals), 0)


if __name__ == "__main__":
    unittest.main()
