from __future__ import annotations

import os
from dataclasses import asdict
from functools import lru_cache
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import EngineConfig, load_config
from .ingestion import items_from_payload
from .pipeline import AnalysisPipeline
from .providers import EbayBrowseProvider, GeminiGroundedResearchProvider, MarketProvider
from .store import EngineStore


app = FastAPI(title="Auction Intelligence Engine", version="1.0.0")
origins = [origin.strip() for origin in os.getenv("AUCTION_ALLOWED_ORIGINS", "http://localhost:3000").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@lru_cache(maxsize=1)
def get_pipeline() -> AnalysisPipeline:
    config = load_config(os.getenv("AUCTION_ENGINE_CONFIG", "engine_config.json"))
    providers: list[MarketProvider] = []
    if os.getenv("EBAY_CLIENT_ID") and os.getenv("EBAY_CLIENT_SECRET"):
        providers.append(EbayBrowseProvider(config))
    if os.getenv("ENABLE_GEMINI_RESEARCH", "").lower() in {"1", "true", "yes"} and os.getenv("GEMINI_API_KEY"):
        providers.append(GeminiGroundedResearchProvider(config))
    return AnalysisPipeline(config, providers, EngineStore(config.runtime.database_path))


@app.get("/api/v1/health")
def health() -> dict[str, Any]:
    pipeline = get_pipeline()
    research_usage = {
        provider.name: provider.usage_status
        for provider in pipeline.providers
        if hasattr(provider, "usage_status")
    }
    return {
        "status": "ok",
        "engineVersion": "1.0.0",
        "providers": [provider.name for provider in pipeline.providers],
        "configHash": pipeline.config.fingerprint()[:12],
        "researchUsage": research_usage,
    }


@app.post("/api/v1/analyze")
def analyze_items(payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload.get("items")
    if not isinstance(rows, list) or not rows:
        raise HTTPException(status_code=422, detail="items must be a non-empty array")
    if len(rows) > 100:
        raise HTTPException(status_code=413, detail="maximum batch size is 100 items")
    try:
        items = items_from_payload(rows)
        results = get_pipeline().analyze_items(items)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"results": [result.to_dict() for result in results]}


@app.post("/api/v1/deep-risk")
def deep_risk(payload: dict[str, Any]) -> dict[str, str]:
    rows = payload.get("items") or ([payload.get("item")] if payload.get("item") else [])
    if not rows:
        raise HTTPException(status_code=422, detail="item is required")
    result = get_pipeline().analyze_item(items_from_payload(rows)[0])
    factors = "; ".join(result.risk_factors) or "No elevated deterministic risk factors detected."
    report = (
        f"Recommendation: {result.recommendation}. Risk {result.risk_score:.0f}/100; "
        f"evidence confidence {result.market.confidence:.0%}. Maximum bid ${result.maximum_bid:.2f}; "
        f"current bid ${result.item.current_bid:.2f}. Downside profit ${result.scenarios[0].net_profit:.2f}. "
        f"Factors: {factors}"
    )
    return {"report": report}


@app.post("/api/v1/chat")
def chat(payload: dict[str, Any]) -> dict[str, str]:
    results = payload.get("results") or []
    if not results:
        return {"answer": "Analyze at least one lot before requesting a portfolio summary."}
    ranked = sorted(results, key=lambda row: row.get("profitAnalysis", {}).get("opportunityScore", 0), reverse=True)
    best = ranked[0]
    profit = best.get("profitAnalysis", {})
    return {
        "answer": (
            f"The highest-ranked lot is {best.get('title', 'Unknown')} at score "
            f"{profit.get('opportunityScore', 0):.0f}, expected profit ${profit.get('netProfit', 0):.2f}, "
            f"and recommendation {profit.get('recommendation', 'RESEARCH')}. Verify its cited comps and condition before bidding."
        )
    }
