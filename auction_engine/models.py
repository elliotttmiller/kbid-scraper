from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


Recommendation = Literal["STRONG_BUY", "BUY", "WATCH", "PASS", "RESEARCH"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AuctionItem:
    item_id: str
    external_id: str
    lot_number: str
    title: str
    auction_title: str
    current_bid: float
    buyers_premium_rate: float | None = None
    buyers_premium_cap: float | None = None
    sales_tax_rate: float | None = None
    category: str = "Uncategorized"
    category_ids: tuple[str, ...] = ()
    description: str = ""
    condition: str = "Unknown"
    quantity: int = 1
    item_url: str = ""
    auction_url: str = ""
    auction_id: str = ""
    image_url: str = ""
    location: str = ""
    item_closing_time: str = ""
    minutes_until_close: float | None = None
    closing_status: str = ""
    prior_expected_profit: float | None = None
    prior_expected_sell_price: float | None = None
    prior_expected_roi: float | None = None
    prior_maximum_bid: float | None = None
    prior_market_confidence: float | None = None
    prior_verified_sold_count: int = 0
    prior_active_listing_count: int = 0
    prior_active_listing_median: float | None = None


@dataclass(frozen=True)
class Comparable:
    source: str
    title: str
    price: float
    shipping: float = 0.0
    listing_type: Literal["sold", "active", "manual"] = "active"
    condition: str = "Unknown"
    url: str = ""
    observed_at: str = field(default_factory=utc_now)
    sold_at: str = ""
    match_score: float = 0.7

    @property
    def delivered_price(self) -> float:
        return max(0.0, self.price) + max(0.0, self.shipping)


@dataclass(frozen=True)
class MarketSnapshot:
    comp_count: int
    sold_count: int
    active_count: int
    low_price: float
    median_price: float
    high_price: float
    confidence: float
    liquidity: float
    price_dispersion: float
    evidence_quality: str
    sources: tuple[str, ...]
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class CostBreakdown:
    hammer_price: float
    buyers_premium: float
    sales_tax: float
    acquisition_total: float
    pickup: float
    outbound_shipping: float
    packaging: float
    labor: float
    storage: float
    refurbishment: float
    platform_fees: float
    return_reserve: float
    total_cost: float


@dataclass(frozen=True)
class ScenarioResult:
    name: str
    sell_price: float
    probability: float
    net_profit: float


@dataclass(frozen=True)
class AnalysisResult:
    item: AuctionItem
    market: MarketSnapshot
    costs: CostBreakdown
    scenarios: tuple[ScenarioResult, ...]
    expected_sell_price: float
    expected_profit: float
    expected_roi: float
    break_even_sell_price: float
    maximum_bid: float
    opportunity_score: float
    risk_score: float
    recommendation: Recommendation
    risk_factors: tuple[str, ...]
    evidence: tuple[Comparable, ...]
    analyzed_at: str = field(default_factory=utc_now)
    engine_version: str = "1.0.0"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def analysis_from_dict(payload: dict[str, Any]) -> AnalysisResult:
    item_data = dict(payload["item"])
    item_data["category_ids"] = tuple(item_data.get("category_ids", ()))
    market_data = dict(payload["market"])
    market_data["sources"] = tuple(market_data.get("sources", ()))
    market_data["notes"] = tuple(market_data.get("notes", ()))
    return AnalysisResult(
        item=AuctionItem(**item_data),
        market=MarketSnapshot(**market_data),
        costs=CostBreakdown(**payload["costs"]),
        scenarios=tuple(ScenarioResult(**entry) for entry in payload.get("scenarios", ())),
        expected_sell_price=payload["expected_sell_price"],
        expected_profit=payload["expected_profit"],
        expected_roi=payload["expected_roi"],
        break_even_sell_price=payload["break_even_sell_price"],
        maximum_bid=payload["maximum_bid"],
        opportunity_score=payload["opportunity_score"],
        risk_score=payload["risk_score"],
        recommendation=payload["recommendation"],
        risk_factors=tuple(payload.get("risk_factors", ())),
        evidence=tuple(Comparable(**entry) for entry in payload.get("evidence", ())),
        analyzed_at=payload.get("analyzed_at", utc_now()),
        engine_version=payload.get("engine_version", "1.0.0"),
    )
