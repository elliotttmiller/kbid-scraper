from __future__ import annotations

import math
import statistics
from datetime import datetime, timezone
from typing import Iterable

from .config import EngineConfig
from .models import Comparable, MarketSnapshot


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _age_score(value: str, stale_after_days: int) -> float:
    try:
        observed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (datetime.now(timezone.utc) - observed).total_seconds() / 86_400)
        return max(0.0, 1.0 - age_days / max(stale_after_days, 1))
    except (TypeError, ValueError):
        return 0.35


def build_market_snapshot(comps: Iterable[Comparable], config: EngineConfig) -> MarketSnapshot:
    valid = tuple(c for c in comps if c.delivered_price > 0 and 0 <= c.match_score <= 1)
    sold = tuple(c for c in valid if c.listing_type in {"sold", "manual"})
    active = tuple(c for c in valid if c.listing_type == "active")
    adjusted = [
        c.delivered_price * (config.market.active_listing_discount if c.listing_type == "active" else 1.0)
        for c in valid
    ]
    if not adjusted:
        return MarketSnapshot(
            comp_count=0,
            sold_count=0,
            active_count=0,
            low_price=0.0,
            median_price=0.0,
            high_price=0.0,
            confidence=0.0,
            liquidity=0.0,
            price_dispersion=1.0,
            evidence_quality="none",
            sources=(),
            notes=("No traceable market comparables were available.",),
        )
    median = statistics.median(adjusted)
    dispersion = statistics.pstdev(adjusted) / median if len(adjusted) > 1 and median else 1.0
    volume_score = min(1.0, len(sold) / 6 + len(active) / 20)
    match_score = statistics.mean(c.match_score for c in valid)
    freshness = statistics.mean(_age_score(c.sold_at or c.observed_at, config.market.stale_after_days) for c in valid)
    confidence = volume_score * 0.35 + match_score * 0.35 + freshness * 0.20 + max(0, 1 - dispersion) * 0.10
    notes: list[str] = []
    if not sold:
        confidence = min(confidence, 0.42)
        notes.append("Active asking prices are discounted and confidence-capped because they are not completed sales.")
    liquidity = min(1.0, len(sold) / max(len(sold) + len(active), 1)) if sold else 0.2
    quality = "high" if confidence >= 0.75 else "medium" if confidence >= 0.5 else "low"
    return MarketSnapshot(
        comp_count=len(valid),
        sold_count=len(sold),
        active_count=len(active),
        low_price=round(_percentile(adjusted, 0.25), 2),
        median_price=round(median, 2),
        high_price=round(_percentile(adjusted, 0.75), 2),
        confidence=round(min(1.0, confidence), 4),
        liquidity=round(liquidity, 4),
        price_dispersion=round(dispersion, 4),
        evidence_quality=quality,
        sources=tuple(sorted({c.source for c in valid})),
        notes=tuple(notes),
    )
