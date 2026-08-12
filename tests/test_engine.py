import csv
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from auction_engine.config import CostConfig, DecisionConfig, EngineConfig, MarketConfig, RuntimeConfig
from auction_engine.ingestion import load_items, parse_time_remaining_minutes, row_to_item
from auction_engine.market import build_market_snapshot
from auction_engine.models import AuctionItem, Comparable
from auction_engine.pipeline import AnalysisPipeline
from auction_engine.providers import GeminiGroundedResearchProvider
from auction_engine.store import EngineStore
from auction_engine.valuation import analyze


def item(**overrides):
    values = {
        "item_id": "item-1",
        "external_id": "client-1",
        "lot_number": "101",
        "title": "Milwaukee M18 Fuel Impact Wrench",
        "auction_title": "Tool Auction",
        "current_bid": 40.0,
        "category": "Power Tools/Shop Equipment",
        "condition": "Used",
    }
    values.update(overrides)
    return AuctionItem(**values)


class IngestionTests(unittest.TestCase):
    def test_money_and_closed_lot_sanitation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lots.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["lot_number", "item_title", "current_bid", "minutes_until_close", "closing_status"])
                writer.writeheader()
                writer.writerow({"lot_number": "1", "item_title": "Open lot", "current_bid": "$1,234.50", "minutes_until_close": "60", "closing_status": "Active"})
                writer.writerow({"lot_number": "2", "item_title": "Closed lot", "current_bid": "$12", "minutes_until_close": "0", "closing_status": "Closing"})
            items, errors = load_items(path)
        self.assertEqual([], errors)
        self.assertEqual(1, len(items))
        self.assertEqual(1234.50, items[0].current_bid)

    def test_invalid_url_is_removed(self):
        parsed = row_to_item({"id": "x", "lot_number": "1", "item_title": "Item", "current_bid": "10", "item_url": "javascript:alert(1)"})
        self.assertEqual("", parsed.item_url)
        self.assertEqual("x", parsed.external_id)

    def test_opportunity_snapshot_fields_are_reingested(self):
        parsed = row_to_item({
            "lot_number": "5",
            "item_title": "Candidate",
            "current_bid": "20",
            "lot_closing_time": "Wed, Aug 12, 2026 06:45 PM CDT",
            "time_remaining": "1d 2h 15m",
            "expected_profit": "125.50",
            "market_confidence": "0.42",
            "verified_sold_comp_count": "2",
            "active_listing_comp_count": "18",
        })
        self.assertEqual(1_575, parsed.minutes_until_close)
        self.assertEqual(125.5, parsed.prior_expected_profit)
        self.assertEqual(2, parsed.prior_verified_sold_count)
        self.assertEqual(18, parsed.prior_active_listing_count)

    def test_time_remaining_parser(self):
        self.assertEqual(3_102, parse_time_remaining_minutes("2d 3h 42m"))
        self.assertEqual(0, parse_time_remaining_minutes("Closed"))


class MarketAndValuationTests(unittest.TestCase):
    def setUp(self):
        self.config = EngineConfig(
            costs=CostConfig(
                buyers_premium_rate=0.18,
                sales_tax_rate=0.0825,
                platform_fee_rate=0.135,
                platform_fixed_fee=0.40,
                pickup_cost=10,
                outbound_shipping=10,
                packaging_cost=3,
                labor_hours=0.5,
                hourly_labor_rate=20,
                storage_cost=2,
                return_rate=0.08,
                return_loss_rate=0.35,
            ),
            decisions=DecisionConfig(minimum_comps=3, minimum_confidence=0.4, target_roi=0.35, minimum_profit=35),
            market=MarketConfig(),
            runtime=RuntimeConfig(database_path=":memory:"),
        )

    def test_active_only_evidence_is_confidence_capped(self):
        comps = [Comparable("ebay", f"Comp {n}", 150 + n, listing_type="active", match_score=0.9) for n in range(10)]
        market = build_market_snapshot(comps, self.config)
        self.assertLessEqual(market.confidence, 0.42)
        self.assertEqual(0, market.sold_count)

    def test_maximum_bid_satisfies_profit_and_roi_targets(self):
        comps = tuple(Comparable("manual", f"Sold {n}", price, listing_type="sold", match_score=0.95) for n, price in enumerate((180, 190, 200, 210, 220, 230)))
        market = build_market_snapshot(comps, self.config)
        result = analyze(item(), market, comps, self.config)
        factor = (1 + self.config.costs.buyers_premium_rate) * (1 + self.config.costs.sales_tax_rate)
        acquisition_at_max = result.maximum_bid * factor
        variable_rate = self.config.costs.platform_fee_rate + self.config.costs.return_rate * self.config.costs.return_loss_rate
        operating = 10 + 10 + 3 + 10 + 2
        profit_at_max = market.median_price * (1 - variable_rate) - self.config.costs.platform_fixed_fee - operating - acquisition_at_max
        self.assertGreaterEqual(profit_at_max + 0.02, self.config.decisions.minimum_profit)
        self.assertGreaterEqual(profit_at_max / acquisition_at_max + 0.0002, self.config.decisions.target_roi)
        self.assertGreater(result.maximum_bid, result.item.current_bid)

    def test_furniture_is_hard_pass(self):
        comps = tuple(Comparable("manual", f"Sold {n}", 1000, listing_type="sold", match_score=0.95) for n in range(6))
        market = build_market_snapshot(comps, self.config)
        result = analyze(item(category="Furniture/Living Room", title="Designer Sofa"), market, comps, self.config)
        self.assertEqual("PASS", result.recommendation)
        self.assertIn("Excluded bulky/furniture category", result.risk_factors)

    def test_buyers_premium_cap_is_applied(self):
        comps = tuple(Comparable("manual", f"Sold {n}", 5000, listing_type="sold", match_score=0.95) for n in range(6))
        market = build_market_snapshot(comps, self.config)
        result = analyze(
            item(current_bid=2000, buyers_premium_rate=0.20, buyers_premium_cap=100),
            market,
            comps,
            self.config,
        )
        self.assertEqual(100, result.costs.buyers_premium)
        self.assertEqual(round(2100 * self.config.costs.sales_tax_rate, 2), result.costs.sales_tax)

    def test_no_evidence_requires_research_or_pass(self):
        market = build_market_snapshot([], self.config)
        result = analyze(item(), market, (), self.config)
        self.assertEqual("RESEARCH", result.recommendation)
        self.assertEqual(0, result.market.confidence)

    def test_resume_rehydrates_prior_results(self):
        class Provider:
            name = "test"

            def __init__(self):
                self.calls = 0

            def fetch(self, _item):
                self.calls += 1
                return [Comparable("test", f"Sold {n}", 200 + n, listing_type="sold", match_score=0.95) for n in range(6)]

        provider = Provider()
        store = EngineStore(":memory:")
        pipeline = AnalysisPipeline(self.config, [provider], store)
        first = pipeline.analyze_items([item()])
        second = pipeline.analyze_items([item()], resume=True)
        store.close()
        self.assertEqual(1, provider.calls)
        self.assertEqual(first[0].to_dict(), second[0].to_dict())

    def test_gemini_provider_accepts_only_grounded_citation_rows(self):
        provider = GeminiGroundedResearchProvider(self.config, api_key="test-key")
        response = SimpleNamespace(
            text='[{"title":"Matching sold tool","price":180,"shipping":10,"listing_type":"sold","condition":"Used","sold_at":"2026-08-01T00:00:00Z","match_score":0.9,"citation_index":0},{"title":"Ungrounded","price":999,"citation_index":4}]',
            candidates=[SimpleNamespace(grounding_metadata=SimpleNamespace(
                grounding_chunks=[SimpleNamespace(web=SimpleNamespace(uri="https://example.com/sold-tool"))],
                grounding_supports=[SimpleNamespace(
                    segment=SimpleNamespace(start_index=0, end_index=160),
                    grounding_chunk_indices=[0],
                )],
            ))],
        )

        class Models:
            def __init__(self):
                self.kwargs = None

            def generate_content(self, **_kwargs):
                self.kwargs = _kwargs
                return response

        models = Models()
        provider.client = SimpleNamespace(models=models)
        comps = provider.fetch(item())
        self.assertEqual(1, len(comps))
        self.assertEqual("sold", comps[0].listing_type)
        self.assertEqual("https://example.com/sold-tool", comps[0].url)
        self.assertEqual("completed", provider.grounded_summary["status"])
        self.assertEqual(1, provider.grounded_summary["acceptedComparables"])
        request_config = models.kwargs["config"].model_dump(exclude_none=True)
        self.assertNotIn("response_mime_type", request_config)
        self.assertEqual(0, request_config["thinking_config"]["thinking_budget"])
        self.assertIn("tools", request_config)

    def test_gemini_triage_is_prepared_from_valued_opportunities(self):
        comps = tuple(
            Comparable("manual", f"Sold {n}", 1000, listing_type="sold", match_score=0.95)
            for n in range(6)
        )
        market = build_market_snapshot(comps, self.config)
        valued = analyze(item(current_bid=40), market, comps, self.config)
        triage_market = replace(
            self.config.market,
            gemini_triage_input_limit=1,
            gemini_triage_min_candidates=1,
            gemini_triage_max_candidates=1,
        )
        provider = GeminiGroundedResearchProvider(replace(self.config, market=triage_market), api_key="test-key")
        captured = []

        def run_triage(items, _limit):
            captured.extend(items)
            return {items[0].item_id}, [{
                "itemId": items[0].item_id,
                "selected": True,
                "strategicScore": 90,
                "reason": "Valued candidate",
            }]

        provider._run_triage = run_triage
        candidates = provider.prepare_from_results([valued])
        self.assertEqual(1, len(candidates))
        self.assertEqual(valued.expected_profit, captured[0].prior_expected_profit)
        self.assertEqual(valued.market.active_count, captured[0].prior_active_listing_count)
        self.assertEqual(valued.market.confidence, captured[0].prior_market_confidence)

    def test_gemini_empty_parse_is_audited_and_not_cached(self):
        provider = GeminiGroundedResearchProvider(self.config, api_key="test-key")

        class Models:
            def __init__(self):
                self.calls = 0

            def generate_content(self, **_kwargs):
                self.calls += 1
                return SimpleNamespace(
                    text='[{"title":"Uncited result","price":200,"listing_type":"active"}]',
                    candidates=[SimpleNamespace(grounding_metadata=SimpleNamespace(
                        grounding_chunks=[], grounding_supports=[]
                    ))],
                    usage_metadata=SimpleNamespace(
                        prompt_token_count=100,
                        candidates_token_count=20,
                        thoughts_token_count=0,
                        total_token_count=120,
                    ),
                )

        models = Models()
        provider.client = SimpleNamespace(models=models)
        store = EngineStore(":memory:")
        pipeline = AnalysisPipeline(self.config, [provider], store)
        pipeline.research(item())
        pipeline.research(item())
        store.close()

        self.assertEqual(2, models.calls)
        summary = provider.grounded_summary
        self.assertEqual("no-usable-evidence", summary["status"])
        self.assertEqual(2, summary["requestsWithoutUsableEvidence"])
        self.assertEqual(2, summary["rejectionReasons"]["missing-grounding-source"])
        self.assertEqual(240, summary["usage"]["totalTokens"])

    def test_gemini_accepts_citation_first_grounded_lines(self):
        provider = GeminiGroundedResearchProvider(self.config, api_key="test-key")
        line = "active | $75.00 | Free shipping | MS65 | | 1941-S Mercury Dime NGC MS65"
        response = SimpleNamespace(
            text=line,
            candidates=[SimpleNamespace(
                finish_reason="STOP",
                grounding_metadata=SimpleNamespace(
                    grounding_chunks=[SimpleNamespace(web=SimpleNamespace(uri="https://example.com/coin"))],
                    grounding_supports=[SimpleNamespace(
                        segment=SimpleNamespace(start_index=0, end_index=len(line), text=line),
                        grounding_chunk_indices=[0],
                    )],
                ),
            )],
        )

        class Models:
            def generate_content(self, **_kwargs):
                return response

        provider.client = SimpleNamespace(models=Models())
        comps = provider.fetch(item(title="1941-S Mercury Dime NGC MS65"))
        self.assertEqual(1, len(comps))
        self.assertEqual(75, comps[0].price)
        self.assertEqual("active", comps[0].listing_type)
        self.assertEqual("https://example.com/coin", comps[0].url)

    def test_gemini_grounded_reports_include_detail_and_summary(self):
        provider = GeminiGroundedResearchProvider(self.config, api_key="test-key")
        provider._append_audit({
            "itemId": "item-1",
            "itemTitle": "Example researched lot",
            "itemUrl": "https://example.com/lot",
            "status": "no-usable-evidence",
            "startedAt": "2026-08-12T00:00:00+00:00",
            "acceptedComparables": 0,
            "groundingSourceCount": 1,
            "rejectionReasons": {"invalid-json": 1},
            "usage": {"totalTokens": 125},
        })
        with tempfile.TemporaryDirectory() as directory:
            detail = Path(directory) / "gemini-grounded-research.jsonl"
            summary_path = Path(directory) / "gemini-grounded-summary.json"
            readable = Path(directory) / "gemini-grounded-report.md"
            summary = provider.write_grounded_reports(detail, summary_path, readable)
            detail_rows = [json.loads(line) for line in detail.read_text(encoding="utf-8").splitlines()]
            disk_summary = json.loads(summary_path.read_text(encoding="utf-8"))
            readable_text = readable.read_text(encoding="utf-8")
        self.assertEqual("no-usable-evidence", summary["status"])
        self.assertEqual("item-1", detail_rows[0]["itemId"])
        self.assertEqual(125, disk_summary["usage"]["totalTokens"])
        self.assertIn("# Gemini Grounded Research Report", readable_text)
        self.assertIn("Example researched lot", readable_text)
        self.assertIn("No cited comparable evidence", readable_text)

    def test_gemini_priority_prefers_liquid_identifiable_lots(self):
        provider = GeminiGroundedResearchProvider(self.config, api_key="test-key")
        generic = item(item_id="generic", title="Miscellaneous household items", category="Small Housewares", current_bid=1)
        collectible = item(item_id="coin", title="1887 Morgan Silver Dollar PCGS MS64", category="Coins", current_bid=50)
        self.assertGreater(provider._priority(collectible), provider._priority(generic))

    def test_gemini_non_grounded_triage_selects_bounded_shortlist(self):
        triage_market = replace(
            self.config.market,
            gemini_triage_input_limit=2,
            gemini_triage_min_candidates=1,
            gemini_triage_max_candidates=1,
        )
        provider = GeminiGroundedResearchProvider(replace(self.config, market=triage_market), api_key="test-key")

        class Models:
            def __init__(self):
                self.kwargs = None

            def generate_content(self, **kwargs):
                self.kwargs = kwargs
                return SimpleNamespace(text='[{"item_id":"best","selected":true,"strategic_score":94,"reason":"Strong identity"},{"item_id":"other","selected":false,"strategic_score":20,"reason":"Weak"}]')

        models = Models()
        provider.client = SimpleNamespace(models=models)
        candidates = [
            item(item_id="best", title="1887 Morgan Dollar PCGS MS64", prior_expected_profit=150),
            item(item_id="other", title="Miscellaneous item", prior_expected_profit=20),
        ]
        provider.prepare(candidates)
        self.assertTrue(provider.should_fetch(candidates[0]))
        self.assertFalse(provider.should_fetch(candidates[1]))
        self.assertEqual("completed", provider.triage_status["status"])
        self.assertEqual(provider._allowed_item_ids, set(provider.triage_status["selectedItemIds"]))
        self.assertNotIn("tools", models.kwargs["config"].model_dump(exclude_none=True))

    def test_gemini_triage_fallback_still_selects_top_fifty(self):
        provider = GeminiGroundedResearchProvider(self.config, api_key="test-key")

        class Models:
            def generate_content(self, **_kwargs):
                raise RuntimeError("simulated triage outage")

        provider.client = SimpleNamespace(models=Models())
        candidates = [
            item(item_id=f"item-{index}", title=f"Collectible model {index}", prior_expected_profit=200-index)
            for index in range(60)
        ]
        provider.prepare(candidates)
        self.assertEqual("fallback", provider.triage_status["status"])
        self.assertEqual(50, len(provider._allowed_item_ids))
        self.assertEqual(provider._allowed_item_ids, set(provider.triage_status["selectedItemIds"]))

    def test_gemini_request_tracking_has_no_budget_ceiling(self):
        provider = GeminiGroundedResearchProvider(self.config, api_key="test-key")
        for _ in range(1_000):
            provider._record_request()
        self.assertEqual(1_000, provider.usage_status["requests"])


if __name__ == "__main__":
    unittest.main()
