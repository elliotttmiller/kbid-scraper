from __future__ import annotations

import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import EngineConfig
from .market import build_market_snapshot
from .models import AnalysisResult, AuctionItem, Comparable
from .providers import MarketProvider
from .store import EngineStore
from .valuation import analyze


logger = logging.getLogger(__name__)


class AnalysisPipeline:
    def __init__(self, config: EngineConfig, providers: list[MarketProvider], store: EngineStore | None = None):
        self.config = config
        self.providers = providers
        self.store = store or EngineStore(config.runtime.database_path)

    def _cache_key(self, provider: MarketProvider, item: AuctionItem) -> str:
        query = f"{provider.name}|{item.title.lower()}|{item.category.lower()}|{item.condition.lower()}"
        return hashlib.sha256(query.encode("utf-8")).hexdigest()

    def research(self, item: AuctionItem) -> tuple[Comparable, ...]:
        evidence: list[Comparable] = []
        for provider in self.providers:
            if getattr(provider, "only_if_no_sold_evidence", False) and any(
                comp.listing_type in {"sold", "manual"} for comp in evidence
            ):
                continue
            cache_key = self._cache_key(provider, item)
            cached = self.store.get_comps(cache_key)
            if cached is not None and (cached or getattr(provider, "cache_empty_results", True)):
                evidence.extend(cached)
                continue
            if hasattr(provider, "should_fetch") and not provider.should_fetch(item):
                continue
            try:
                comps = provider.fetch(item)
            except Exception as exc:  # provider failure must not abort the batch
                logger.warning("Market provider %s failed for %s: %s", provider.name, item.item_id, exc)
                continue
            if comps or getattr(provider, "cache_empty_results", True):
                self.store.put_comps(cache_key, comps, self.config.market.cache_ttl_hours)
            evidence.extend(comps)
        deduplicated: dict[tuple[str, str, float], Comparable] = {}
        for comp in evidence:
            key = (comp.source, comp.url or comp.title.lower(), comp.delivered_price)
            current = deduplicated.get(key)
            if current is None or comp.match_score > current.match_score:
                deduplicated[key] = comp
        return tuple(deduplicated.values())

    def analyze_item(self, item: AuctionItem) -> AnalysisResult:
        evidence = self.research(item)
        market = build_market_snapshot(evidence, self.config)
        result = analyze(item, market, evidence, self.config)
        self.store.put_result(result, self.config.fingerprint())
        return result

    def analyze_items(self, items: list[AuctionItem], resume: bool = False) -> list[AnalysisResult]:
        config_hash = self.config.fingerprint()
        results: list[AnalysisResult] = []
        pending: list[AuctionItem] = []
        for item in items:
            cached = self.store.get_result(item.item_id, config_hash) if resume else None
            if cached is not None:
                results.append(cached)
            else:
                pending.append(item)
        for provider in self.providers:
            prepare = getattr(provider, "prepare", None)
            if prepare:
                prepare(pending)
        total = len(pending)
        completed = 0
        logger.info("Starting valuation for %d lots (%d restored from checkpoint)", total, len(results))
        with ThreadPoolExecutor(max_workers=min(self.config.runtime.workers, max(1, len(pending)))) as executor:
            futures = {executor.submit(self.analyze_item, item): item for item in pending}
            for future in as_completed(futures):
                item = futures[future]
                try:
                    results.append(future.result())
                except Exception as exc:
                    logger.exception("Analysis failed for %s: %s", item.item_id, exc)
                finally:
                    completed += 1
                    if completed == total or completed % 5 == 0:
                        logger.info("Valuation progress: %d/%d lots completed", completed, total)
        return sorted(results, key=lambda result: result.opportunity_score, reverse=True)
