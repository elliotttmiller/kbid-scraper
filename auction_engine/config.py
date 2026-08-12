from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CostConfig:
    buyers_premium_rate: float = 0.18
    sales_tax_rate: float = 0.0825
    platform_fee_rate: float = 0.135
    platform_fixed_fee: float = 0.40
    pickup_cost: float = 18.00
    outbound_shipping: float = 15.00
    packaging_cost: float = 4.00
    labor_hours: float = 0.75
    hourly_labor_rate: float = 20.00
    storage_cost: float = 3.00
    refurbishment_reserve: float = 0.00
    return_rate: float = 0.08
    return_loss_rate: float = 0.35


@dataclass(frozen=True)
class DecisionConfig:
    minimum_comps: int = 3
    minimum_confidence: float = 0.45
    target_roi: float = 0.35
    minimum_profit: float = 35.00
    strong_buy_score: float = 78.0
    buy_score: float = 62.0
    watch_score: float = 45.0
    maximum_risk_score: float = 72.0
    exclude_category_terms: tuple[str, ...] = (
        "furniture",
        "mattress",
        "sofa",
        "couch",
        "bedroom",
        "dining",
        "living room",
    )


@dataclass(frozen=True)
class MarketConfig:
    cache_ttl_hours: int = 24
    max_comps_per_provider: int = 20
    active_listing_discount: float = 0.82
    stale_after_days: int = 120
    scenario_probabilities: tuple[float, float, float] = (0.25, 0.50, 0.25)
    gemini_model: str = "gemini-2.5-flash"
    gemini_max_output_tokens: int = 1200
    gemini_concurrency: int = 2
    gemini_triage_enabled: bool = True
    gemini_triage_model: str = "gemini-3.1-flash-lite"
    gemini_triage_input_limit: int = 100
    gemini_triage_min_candidates: int = 50
    gemini_triage_max_candidates: int = 50
    gemini_triage_max_output_tokens: int = 4000


@dataclass(frozen=True)
class RuntimeConfig:
    workers: int = 6
    request_timeout_seconds: float = 15.0
    retry_attempts: int = 3
    retry_backoff_seconds: float = 0.5
    database_path: str = "results/shared/cache/auction-engine.sqlite3"


@dataclass(frozen=True)
class EngineConfig:
    costs: CostConfig = field(default_factory=CostConfig)
    decisions: DecisionConfig = field(default_factory=DecisionConfig)
    market: MarketConfig = field(default_factory=MarketConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)

    def fingerprint(self) -> str:
        payload = json.dumps(
            {"costs": asdict(self.costs), "decisions": asdict(self.decisions), "market": asdict(self.market)},
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(payload.encode("utf-8")).hexdigest()


def _merge_dataclass(instance: Any, values: dict[str, Any]) -> Any:
    allowed = instance.__dataclass_fields__
    normalized = {
        key: tuple(value) if key == "exclude_category_terms" and isinstance(value, list) else value
        for key, value in values.items()
        if key in allowed
    }
    return type(instance)(**{**asdict(instance), **normalized})


def load_config(path: str | Path | None = None) -> EngineConfig:
    config = EngineConfig()
    candidate = Path(path or os.getenv("AUCTION_ENGINE_CONFIG", "engine_config.json"))
    if candidate.exists():
        with candidate.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        config = EngineConfig(
            costs=_merge_dataclass(config.costs, raw.get("costs", {})),
            decisions=_merge_dataclass(config.decisions, raw.get("decisions", {})),
            market=_merge_dataclass(config.market, raw.get("market", {})),
            runtime=_merge_dataclass(config.runtime, raw.get("runtime", {})),
        )
        if not Path(config.runtime.database_path).is_absolute():
            config = EngineConfig(
                costs=config.costs,
                decisions=config.decisions,
                market=config.market,
                runtime=_merge_dataclass(
                    config.runtime,
                    {"database_path": str((candidate.resolve().parent / config.runtime.database_path).resolve())},
                ),
            )
    _validate(config)
    return config


def _validate(config: EngineConfig) -> None:
    rates = {
        "buyers_premium_rate": config.costs.buyers_premium_rate,
        "sales_tax_rate": config.costs.sales_tax_rate,
        "platform_fee_rate": config.costs.platform_fee_rate,
        "return_rate": config.costs.return_rate,
        "return_loss_rate": config.costs.return_loss_rate,
        "target_roi": config.decisions.target_roi,
        "active_listing_discount": config.market.active_listing_discount,
    }
    for name, value in rates.items():
        if not 0 <= value < 1:
            raise ValueError(f"{name} must be between 0 and 1 (exclusive of 1)")
    probabilities = config.market.scenario_probabilities
    if len(probabilities) != 3 or abs(sum(probabilities) - 1.0) > 1e-9:
        raise ValueError("scenario_probabilities must contain three values summing to 1")
    if config.runtime.workers < 1 or config.decisions.minimum_comps < 1:
        raise ValueError("workers and minimum_comps must be positive")
    if not 1 <= config.market.gemini_triage_min_candidates <= config.market.gemini_triage_max_candidates:
        raise ValueError("Gemini triage candidate limits are invalid")
    if config.market.gemini_triage_input_limit < config.market.gemini_triage_max_candidates:
        raise ValueError("gemini_triage_input_limit must cover gemini_triage_max_candidates")
