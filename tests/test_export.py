import csv
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from auction_engine.export import CSV_FIELDS, _remaining_text, is_opportunity, write_opportunity_analysis_report, write_results


class OpportunityExportTests(unittest.TestCase):
    def test_csv_is_decision_focused(self):
        excluded = {
            "buyers_premium_rate",
            "buyers_premium_cap",
            "sales_tax_rate",
            "break_even_sell_price",
            "low_price",
            "median_price",
            "high_price",
            "evidence_sources",
            "analyzed_at",
        }
        self.assertTrue(excluded.isdisjoint(CSV_FIELDS))
        self.assertEqual(
            (
                "time_remaining", "item_title", "expected_profit", "current_bid", "expected_sell_price",
                "expected_roi_percent", "maximum_bid",
                "lot_closing_time", "market_confidence",
                "verified_sold_comp_count", "verified_sold_median_price",
                "active_listing_comp_count", "ebay_active_listing_count",
                "active_listing_median_price", "lot_number",
                "auction_title", "category", "location",
                "item_url", "risk_factors", "opportunity_score", "risk_score", "rank",
                "recommendation",
            ),
            CSV_FIELDS,
        )

    def test_empty_csv_still_has_stable_header(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "opportunities.csv"
            write_results([], target)
            with target.open(encoding="utf-8", newline="") as handle:
                self.assertEqual(list(CSV_FIELDS), next(csv.reader(handle)))

    def test_csv_excludes_non_viable_analyzed_rows(self):
        def result(profit, maximum_bid, current_bid, recommendation):
            return SimpleNamespace(
                recommendation=recommendation,
                expected_profit=profit,
                maximum_bid=maximum_bid,
                item=SimpleNamespace(current_bid=current_bid),
            )

        rows = [
            result(-5, 0, 20, "PASS"),
            result(25, 15, 20, "PASS"),
            result(40, 50, 20, "RESEARCH"),
        ]
        self.assertEqual([False, False, True], [is_opportunity(row) for row in rows])

    def test_remaining_time_is_human_readable(self):
        self.assertEqual("2d 3h 42m", _remaining_text(3_102))
        self.assertEqual("Closed", _remaining_text(0))

    def test_opportunity_analysis_report_combines_decision_and_research(self):
        evidence = SimpleNamespace(
            source="ebay_browse", listing_type="active", delivered_price=120,
        )
        result = SimpleNamespace(
            recommendation="BUY", expected_profit=75.0, expected_roi=80.0,
            expected_sell_price=200.0, maximum_bid=60.0, opportunity_score=78.0,
            risk_score=35.0, risk_factors=("Condition risk",), analyzed_at="2026-08-12T00:00:00+00:00",
            item=SimpleNamespace(
                item_id="target-1", title="Test Target", item_url="https://example.com/lot",
                current_bid=25.0, minutes_until_close=120, item_closing_time="",
            ),
            market=SimpleNamespace(sold_count=1, active_count=1, confidence=0.7),
            evidence=(evidence,),
        )
        triage = {"decisions": [{
            "itemId": "target-1", "selected": True, "strategicScore": 90,
            "reason": "Strong target",
        }]}
        audits = [{
            "itemId": "target-1", "acceptedEvidence": [{
                "listing_type": "sold", "title": "Comparable target",
                "delivered_price": 180, "condition": "Used", "sold_at": "2026-08-01",
                "url": "https://example.com/comp",
            }],
        }]
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "opportunity-analysis-report.md"
            count = write_opportunity_analysis_report([result], triage, audits, target)
            text = target.read_text(encoding="utf-8")
        self.assertEqual(1, count)
        self.assertIn("# Auction Opportunity Analysis Report", text)
        self.assertIn("Test Target", text)
        self.assertIn("$75.00", text)
        self.assertIn("Comparable target", text)
        self.assertIn("Strong target", text)


if __name__ == "__main__":
    unittest.main()
