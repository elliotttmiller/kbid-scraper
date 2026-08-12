from __future__ import annotations

import base64
import csv
import json
import logging
import os
import math
import threading
import time
from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

import requests

from .config import EngineConfig
from .ingestion import clean_text, parse_money, safe_url
from .models import AnalysisResult, AuctionItem, Comparable


logger = logging.getLogger(__name__)


class MarketProvider(Protocol):
    name: str

    def fetch(self, item: AuctionItem) -> list[Comparable]: ...


class ManualComparableProvider:
    """Loads analyst-verified sold or manual comps from a CSV file.

    Rows are matched by item_key, item_url, or auction_id + lot_number.
    """

    name = "manual"

    def __init__(self, path: str | Path):
        self._rows: dict[str, list[Comparable]] = defaultdict(list)
        with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"price", "title"}
            missing = required.difference(reader.fieldnames or [])
            if missing:
                raise ValueError(f"manual comps CSV missing columns: {', '.join(sorted(missing))}")
            for row in reader:
                key = clean_text(row.get("item_key") or row.get("item_url"))
                if not key:
                    key = f"{clean_text(row.get('auction_id'))}:{clean_text(row.get('lot_number'))}"
                listing_type = clean_text(row.get("listing_type")).lower()
                if listing_type not in {"sold", "active", "manual"}:
                    listing_type = "manual"
                comp = Comparable(
                    source=clean_text(row.get("source")) or "manual",
                    title=clean_text(row.get("title"), 500),
                    price=parse_money(row.get("price")),
                    shipping=parse_money(row.get("shipping")),
                    listing_type=listing_type,  # type: ignore[arg-type]
                    condition=clean_text(row.get("condition"), 100) or "Unknown",
                    url=safe_url(row.get("url")),
                    observed_at=clean_text(row.get("observed_at")) or datetime.now(timezone.utc).isoformat(),
                    sold_at=clean_text(row.get("sold_at")),
                    match_score=max(0.0, min(1.0, float(row.get("match_score") or 0.85))),
                )
                if comp.price > 0:
                    self._rows[key].append(comp)

    def fetch(self, item: AuctionItem) -> list[Comparable]:
        keys = (item.item_id, item.item_url, f"{item.auction_id}:{item.lot_number}")
        for key in keys:
            if key and key in self._rows:
                return list(self._rows[key])
        return []


class EbayBrowseProvider:
    """Fetches current eBay asking-price evidence through the official Browse API.

    Browse results are active listings, never represented as sold transactions.
    """

    name = "ebay_browse"
    token_url = "https://api.ebay.com/identity/v1/oauth2/token"
    search_url = "https://api.ebay.com/buy/browse/v1/item_summary/search"

    def __init__(self, config: EngineConfig, client_id: str | None = None, client_secret: str | None = None):
        self.config = config
        self.client_id = client_id or os.getenv("EBAY_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("EBAY_CLIENT_SECRET", "")
        if not self.client_id or not self.client_secret:
            raise ValueError("EBAY_CLIENT_ID and EBAY_CLIENT_SECRET are required for eBay research")
        self._local = threading.local()
        self._token = ""
        self._token_expires_at = 0.0
        self._lock = threading.Lock()

    def _session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            self._local.session = session
        return session

    def _access_token(self) -> str:
        with self._lock:
            if self._token and time.time() < self._token_expires_at - 60:
                return self._token
            basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
            response = self._session().post(
                self.token_url,
                headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
                data={"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"},
                timeout=self.config.runtime.request_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            self._token = payload["access_token"]
            self._token_expires_at = time.time() + int(payload.get("expires_in", 7200))
            return self._token

    def fetch(self, item: AuctionItem) -> list[Comparable]:
        query = " ".join(item.title.split()[:14])
        headers = {
            "Authorization": f"Bearer {self._access_token()}",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
            "Accept-Language": "en-US",
        }
        params = {
            "q": query,
            "limit": str(self.config.market.max_comps_per_provider),
            "filter": "buyingOptions:{FIXED_PRICE}",
        }
        error: Exception | None = None
        for attempt in range(self.config.runtime.retry_attempts):
            try:
                response = self._session().get(
                    self.search_url,
                    headers=headers,
                    params=params,
                    timeout=self.config.runtime.request_timeout_seconds,
                )
                response.raise_for_status()
                return self._parse(response.json(), item)
            except requests.RequestException as exc:
                error = exc
                if attempt + 1 < self.config.runtime.retry_attempts:
                    time.sleep(self.config.runtime.retry_backoff_seconds * (2**attempt))
        raise RuntimeError(f"eBay Browse request failed: {error}")

    def _parse(self, payload: dict, item: AuctionItem) -> list[Comparable]:
        title_terms = {term.lower() for term in item.title.split() if len(term) > 2}
        comps: list[Comparable] = []
        for result in payload.get("itemSummaries", []):
            price = result.get("price", {}).get("value", 0)
            shipping_options = result.get("shippingOptions") or []
            shipping = shipping_options[0].get("shippingCost", {}).get("value", 0) if shipping_options else 0
            comp_title = clean_text(result.get("title"), 500)
            comp_terms = {term.lower() for term in comp_title.split() if len(term) > 2}
            overlap = len(title_terms & comp_terms) / max(len(title_terms), 1)
            comps.append(
                Comparable(
                    source=self.name,
                    title=comp_title,
                    price=parse_money(price),
                    shipping=parse_money(shipping),
                    listing_type="active",
                    condition=clean_text(result.get("condition"), 100) or "Unknown",
                    url=safe_url(result.get("itemWebUrl")),
                    observed_at=datetime.now(timezone.utc).isoformat(),
                    match_score=max(0.25, min(0.95, overlap)),
                )
            )
        return [comp for comp in comps if comp.price > 0]


class GeminiGroundedResearchProvider:
    """Uses Gemini only to find compact, cited online comparable evidence."""

    name = "gemini_grounded"
    only_if_no_sold_evidence = True
    cache_empty_results = False

    def __init__(self, config: EngineConfig, api_key: str | None = None):
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError("Install google-genai to enable Gemini grounded research") from exc
        key = api_key or os.getenv("GEMINI_API_KEY", "")
        if not key:
            raise ValueError("GEMINI_API_KEY is required for Gemini grounded research")
        self.config = config
        self.client = genai.Client(api_key=key)
        self.types = types
        self._requests = 0
        self._budget_lock = threading.Lock()
        self._request_slots = threading.BoundedSemaphore(config.market.gemini_concurrency)
        self._allowed_item_ids: set[str] | None = None
        self.triage_status: dict[str, object] = {"status": "not-run"}
        self._audit_records: list[dict[str, object]] = []
        self._audit_lock = threading.Lock()
        self._prepared = False

    def prepare(self, items: list[AuctionItem]) -> None:
        if self._prepared:
            return
        self._prepared = True
        if not items:
            self._allowed_item_ids = set()
            self.triage_status = {
                "status": "completed",
                "model": self.config.market.gemini_triage_model,
                "groundingEnabled": False,
                "inputCandidates": 0,
                "selectedCandidates": 0,
                "selectedItemIds": [],
                "decisions": [],
            }
            return
        ranked = sorted(items, key=self._priority, reverse=True)
        grounded_limit = min(len(ranked), self.config.market.gemini_triage_max_candidates)
        if not self.config.market.gemini_triage_enabled:
            selected = ranked[:grounded_limit]
            self._allowed_item_ids = {item.item_id for item in selected}
            self.triage_status = {
                "status": "disabled",
                "inputCandidates": len(ranked),
                "selectedCandidates": len(selected),
                "selectedItemIds": [item.item_id for item in selected],
            }
            return
        triage_pool = ranked[:self.config.market.gemini_triage_input_limit]
        try:
            selected_ids, decisions = self._run_triage(triage_pool, grounded_limit)
            minimum = min(self.config.market.gemini_triage_min_candidates, grounded_limit, len(triage_pool))
            if len(selected_ids) < minimum:
                raise ValueError(f"Triage selected only {len(selected_ids)} candidates; minimum is {minimum}")
            decisions = [
                {**decision, "selected": decision.get("itemId") in selected_ids}
                for decision in decisions
            ]
            self._allowed_item_ids = selected_ids
            self.triage_status = {
                "status": "completed",
                "model": self.config.market.gemini_triage_model,
                "groundingEnabled": False,
                "inputCandidates": len(triage_pool),
                "selectedCandidates": len(selected_ids),
                "selectedItemIds": sorted(selected_ids),
                "decisions": decisions,
            }
        except Exception as exc:
            fallback = triage_pool[:grounded_limit]
            self._allowed_item_ids = {item.item_id for item in fallback}
            self.triage_status = {
                "status": "fallback",
                "error": clean_text(exc, 500),
                "groundingEnabled": False,
                "inputCandidates": len(triage_pool),
                "selectedCandidates": len(fallback),
                "selectedItemIds": [item.item_id for item in fallback],
            }
            logger.warning("Gemini triage failed; using deterministic shortlist: %s", exc)

    def prepare_from_results(self, results: list[AnalysisResult]) -> list[AuctionItem]:
        from .export import is_opportunity

        candidates = [
            replace(
                result.item,
                prior_expected_profit=result.expected_profit,
                prior_expected_sell_price=result.expected_sell_price,
                prior_expected_roi=result.expected_roi,
                prior_maximum_bid=result.maximum_bid,
                prior_market_confidence=result.market.confidence,
                prior_verified_sold_count=result.market.sold_count,
                prior_active_listing_count=result.market.active_count,
                prior_active_listing_median=result.market.median_price if result.market.active_count else None,
            )
            for result in results
            if is_opportunity(result)
        ]
        self.prepare(candidates)
        return candidates

    def _run_triage(self, items: list[AuctionItem], limit: int) -> tuple[set[str], list[dict[str, object]]]:
        payload = [{
            "item_id": item.item_id,
            "title": item.title,
            "category": item.category,
            "current_bid": item.current_bid,
            "minutes_remaining": item.minutes_until_close,
            "expected_profit": item.prior_expected_profit,
            "market_confidence": item.prior_market_confidence,
            "verified_sold_count": item.prior_verified_sold_count,
            "ebay_active_count": item.prior_active_listing_count,
        } for item in items]
        prompt = f"""Audit these pre-screened auction opportunities using only the supplied data. Do not search the web.
Select exactly the top {min(limit, len(items))} lots that most deserve expensive grounded resale research.
Prioritize imminent closings, credible positive profit, identifiable exact products, useful eBay evidence,
and realistic resale liquidity. Reject generic identities, suspicious profit/ROI, weak match evidence,
bulky resale burdens, and likely accessory/model mismatches. Never invent prices or facts.
Return one compact JSON array. Each object: item_id, selected (boolean), strategic_score (0-100), reason (max 120 chars).
Candidates:
{json.dumps(payload, separators=(',', ':'))}"""
        response = self.client.models.generate_content(
            model=self.config.market.gemini_triage_model,
            contents=prompt,
            config=self.types.GenerateContentConfig(
                max_output_tokens=self.config.market.gemini_triage_max_output_tokens,
                response_mime_type="application/json",
            ),
        )
        raw = json.loads(response.text or "[]")
        if not isinstance(raw, list):
            raise ValueError("Triage response must be a JSON array")
        allowed = {item.item_id for item in items}
        decisions = []
        for row in raw:
            if not isinstance(row, dict) or row.get("item_id") not in allowed:
                continue
            decisions.append({
                "itemId": row["item_id"],
                "selected": bool(row.get("selected")),
                "strategicScore": max(0.0, min(100.0, float(row.get("strategic_score") or 0))),
                "reason": clean_text(row.get("reason"), 120),
            })
        selected = sorted(
            decisions,
            key=lambda row: (bool(row["selected"]), float(row["strategicScore"])),
            reverse=True,
        )[:limit]
        return {str(row["itemId"]) for row in selected}, decisions

    def should_fetch(self, item: AuctionItem) -> bool:
        return self._allowed_item_ids is None or item.item_id in self._allowed_item_ids

    @property
    def selected_item_count(self) -> int:
        return len(self._allowed_item_ids or ())

    def _priority(self, item: AuctionItem) -> float:
        text = f"{item.category} {item.title}".lower()
        if any(term in text for term in self.config.decisions.exclude_category_terms):
            return -10_000
        category_terms = {
            "coin": 28, "currency": 24, "precious": 28, "jewelry": 25,
            "trading card": 24, "collectible": 18, "power tool": 22,
            "electronics": 17, "camera": 20, "firearm": 20, "vehicle": 15,
            "commercial": 12, "industrial": 15,
        }
        score = sum(weight for term, weight in category_terms.items() if term in text)
        if item.prior_expected_profit is not None:
            score += min(55, math.log1p(max(0, item.prior_expected_profit)) * 9)
        if item.prior_market_confidence is not None:
            score += item.prior_market_confidence * 15
        score += min(12, item.prior_verified_sold_count * 3)
        score += min(10, item.prior_active_listing_count * 0.5)
        title_tokens = [token for token in item.title.split() if len(token) >= 3]
        score += min(18, len(title_tokens) * 1.5)
        score += min(12, sum(character.isdigit() for character in item.title) * 2)
        if item.condition.lower() not in {"", "unknown"}:
            score += 5
        if item.minutes_until_close is not None:
            score += max(0, 24 - item.minutes_until_close / (3 * 60))
        score -= min(20, math.log1p(max(0, item.current_bid)) * 2.5)
        return score

    def _record_request(self) -> None:
        with self._budget_lock:
            self._requests += 1

    @property
    def usage_status(self) -> dict[str, float | int]:
        with self._budget_lock:
            return {"requests": self._requests}

    def _append_audit(self, record: dict[str, object]) -> None:
        with self._audit_lock:
            self._audit_records.append(record)

    @staticmethod
    def _usage_metadata(response) -> dict[str, int]:
        usage = getattr(response, "usage_metadata", None)
        fields = {
            "promptTokens": "prompt_token_count",
            "candidateTokens": "candidates_token_count",
            "thinkingTokens": "thoughts_token_count",
            "totalTokens": "total_token_count",
        }
        return {
            output: int(getattr(usage, source, 0) or 0)
            for output, source in fields.items()
        }

    @property
    def grounded_summary(self) -> dict[str, object]:
        with self._audit_lock:
            records = list(self._audit_records)
        status_counts: dict[str, int] = defaultdict(int)
        rejection_counts: dict[str, int] = defaultdict(int)
        accepted_comparables = 0
        grounding_sources = 0
        token_totals: dict[str, int] = defaultdict(int)
        for record in records:
            status_counts[str(record.get("status") or "unknown")] += 1
            accepted_comparables += int(record.get("acceptedComparables") or 0)
            grounding_sources += int(record.get("groundingSourceCount") or 0)
            for reason, count in (record.get("rejectionReasons") or {}).items():
                rejection_counts[str(reason)] += int(count)
            for name, count in (record.get("usage") or {}).items():
                token_totals[str(name)] += int(count)
        attempted = len(records)
        successful = status_counts.get("accepted", 0)
        return {
            "status": "completed" if accepted_comparables > 0 else ("no-usable-evidence" if attempted else "not-run"),
            "model": self.config.market.gemini_model,
            "requestsAttempted": attempted,
            "requestsWithAcceptedEvidence": successful,
            "requestsWithoutUsableEvidence": status_counts.get("no-usable-evidence", 0),
            "requestsFailed": status_counts.get("failed", 0),
            "acceptedComparables": accepted_comparables,
            "groundingSourceCount": grounding_sources,
            "rejectionReasons": dict(sorted(rejection_counts.items())),
            "usage": dict(sorted(token_totals.items())),
            "generatedAt": datetime.now(timezone.utc).isoformat(),
        }

    @property
    def audit_records(self) -> list[dict[str, object]]:
        with self._audit_lock:
            return [dict(record) for record in self._audit_records]

    @staticmethod
    def _markdown_text(value: object) -> str:
        return clean_text(value, 1_000).replace("|", "\\|").replace("\n", " ")

    def write_grounded_reports(
        self,
        detail_path: str | Path,
        summary_path: str | Path,
        readable_path: str | Path | None = None,
    ) -> dict[str, object]:
        with self._audit_lock:
            records = sorted(self._audit_records, key=lambda row: str(row.get("startedAt") or ""))
        detail_target = Path(detail_path)
        detail_target.parent.mkdir(parents=True, exist_ok=True)
        temp_detail = detail_target.with_suffix(detail_target.suffix + ".tmp")
        with temp_detail.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, separators=(",", ":")) + "\n")
        temp_detail.replace(detail_target)
        summary = self.grounded_summary
        summary_target = Path(summary_path)
        summary_target.parent.mkdir(parents=True, exist_ok=True)
        temp_summary = summary_target.with_suffix(summary_target.suffix + ".tmp")
        temp_summary.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        temp_summary.replace(summary_target)
        if readable_path is not None:
            report_target = Path(readable_path)
            report_target.parent.mkdir(parents=True, exist_ok=True)
            lines = [
                "# Gemini Grounded Research Report",
                "",
                f"- Status: **{summary['status']}**",
                f"- Model: `{summary['model']}`",
                f"- Requests: {summary['requestsAttempted']}",
                f"- Requests with evidence: {summary['requestsWithAcceptedEvidence']}",
                f"- Accepted comparables: {summary['acceptedComparables']}",
                f"- Grounding sources: {summary['groundingSourceCount']}",
                f"- Failed requests: {summary['requestsFailed']}",
                f"- Total tokens: {summary.get('usage', {}).get('totalTokens', 0)}",
                "",
            ]
            for index, record in enumerate(records, start=1):
                title = self._markdown_text(record.get("itemTitle") or "Untitled lot")
                lines.extend([
                    f"## {index}. {title}",
                    "",
                    f"- Research status: **{record.get('status', 'unknown')}**",
                    f"- Auction lot: [{self._markdown_text(record.get('itemUrl') or 'No URL')}]({record.get('itemUrl') or ''})",
                    f"- Accepted comparables: {record.get('acceptedComparables', 0)}",
                    f"- Grounding sources: {record.get('groundingSourceCount', 0)}",
                    f"- Tokens: {(record.get('usage') or {}).get('totalTokens', 0)}",
                    "",
                ])
                evidence = record.get("acceptedEvidence") or []
                if evidence:
                    lines.extend([
                        "| Type | Comparable | Price | Shipping | Delivered | Condition | Sold date | Source |",
                        "|---|---|---:|---:|---:|---|---|---|",
                    ])
                    for comp in evidence:
                        url = comp.get("url") or ""
                        source = f"[Open source]({url})" if url else "Unavailable"
                        lines.append(
                            f"| {self._markdown_text(comp.get('listing_type'))} "
                            f"| {self._markdown_text(comp.get('title'))} "
                            f"| ${float(comp.get('price') or 0):,.2f} "
                            f"| ${float(comp.get('shipping') or 0):,.2f} "
                            f"| ${float(comp.get('delivered_price') or 0):,.2f} "
                            f"| {self._markdown_text(comp.get('condition'))} "
                            f"| {self._markdown_text(comp.get('sold_at')) or '-'} | {source} |"
                        )
                    lines.append("")
                else:
                    lines.extend(["No cited comparable evidence was accepted for this lot.", ""])
                rejections = record.get("rejectionReasons") or {}
                if rejections:
                    reason_text = ", ".join(f"{name}: {count}" for name, count in sorted(rejections.items()))
                    lines.extend([f"Rejected evidence: {self._markdown_text(reason_text)}", ""])
            temp_report = report_target.with_suffix(report_target.suffix + ".tmp")
            temp_report.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
            temp_report.replace(report_target)
        return summary

    def fetch(self, item: AuctionItem) -> list[Comparable]:
        self._record_request()
        started_at = datetime.now(timezone.utc).isoformat()
        prompt = f"""You must use the Google Search tool before answering. Find current, traceable resale comparables for this auction lot.

Item: {item.title}
Description: {item.description[:800]}
Category: {item.category}
Condition stated by auction: {item.condition}

Return one result per line in exactly this compact format:
TYPE | PRICE | SHIPPING | CONDITION | SOLD_DATE_OR_EMPTY | TITLE
TYPE must be active or sold. Return at most 5 lines with no introduction, bullets, Markdown, or explanation.
Do not estimate prices. Do not include a row unless a grounding source displays its price and listing status.
Prefer completed/sold evidence from the last 120 days. Exclude accessories, parts, wrong models, and sponsored summaries.
If Google Search is not used or no traceable priced result is found, return exactly NONE."""
        types = self.types
        try:
            with self._request_slots:
                response = self.client.models.generate_content(
                    model=self.config.market.gemini_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                    max_output_tokens=self.config.market.gemini_max_output_tokens,
                ),
            )
        except Exception as exc:
            self._append_audit({
                "itemId": item.item_id,
                "itemTitle": item.title,
                "itemUrl": item.item_url,
                "model": self.config.market.gemini_model,
                "status": "failed",
                "startedAt": started_at,
                "completedAt": datetime.now(timezone.utc).isoformat(),
                "acceptedComparables": 0,
                "groundingSourceCount": 0,
                "rejectionReasons": {"request-failed": 1},
                "error": clean_text(exc, 500),
            })
            raise
        chunks = []
        candidates = getattr(response, "candidates", None) or []
        finish_reasons = [clean_text(getattr(candidate, "finish_reason", ""), 100) for candidate in candidates]
        if candidates:
            metadata = getattr(candidates[0], "grounding_metadata", None)
            chunks = list(getattr(metadata, "grounding_chunks", None) or [])
        urls: list[str] = []
        for chunk in chunks:
            web = getattr(chunk, "web", None)
            urls.append(safe_url(getattr(web, "uri", "")) if web else "")
        supports = []
        if candidates:
            metadata = getattr(candidates[0], "grounding_metadata", None)
            supports = list(getattr(metadata, "grounding_supports", None) or [])
        raw_text = response.text or ""
        rejection_reasons: dict[str, int] = defaultdict(int)
        comps: list[Comparable] = []
        response_row_count = 0
        title_terms = {term.lower() for term in item.title.split() if len(term) > 2}
        for support in supports:
            segment = getattr(support, "segment", None)
            line = clean_text(getattr(segment, "text", "") if segment else "", 1_000)
            parts = [part.strip() for part in line.split("|", 5)]
            if len(parts) != 6:
                rejection_reasons["unsupported-grounded-line"] += 1
                continue
            response_row_count += 1
            listing_type, price, shipping, condition, sold_at, title = parts
            listing_type = listing_type.lower()
            indices = list(getattr(support, "grounding_chunk_indices", None) or [])
            source_url = next((urls[index] for index in indices if 0 <= index < len(urls) and urls[index]), "")
            if not source_url:
                rejection_reasons["missing-grounding-source"] += 1
                continue
            if listing_type not in {"sold", "active"}:
                rejection_reasons["invalid-listing-type"] += 1
                continue
            comp_terms = {term.lower() for term in title.split() if len(term) > 2}
            overlap = len(title_terms & comp_terms) / max(len(title_terms), 1)
            comp = Comparable(
                source=self.name,
                title=clean_text(title, 500),
                price=parse_money(price),
                shipping=parse_money(shipping),
                listing_type=listing_type,  # type: ignore[arg-type]
                condition=clean_text(condition, 100) or "Unknown",
                url=source_url,
                observed_at=datetime.now(timezone.utc).isoformat(),
                sold_at=clean_text(sold_at),
                match_score=max(0.25, min(0.95, overlap)),
            )
            if comp.price > 0 and comp.title:
                comps.append(comp)
            else:
                rejection_reasons["missing-title-or-price"] += 1

        # Compatibility fallback for older JSON-shaped grounded responses.
        rows = []
        if not comps and raw_text.lstrip().startswith(("[", "```")):
            json_text = raw_text.strip()
            if json_text.startswith("```"):
                json_text = json_text.replace("```json", "", 1).replace("```", "").strip()
            try:
                rows = json.loads(json_text)
            except (TypeError, json.JSONDecodeError):
                rejection_reasons["invalid-json"] += 1
            if not isinstance(rows, list):
                rows = []
                rejection_reasons["response-not-array"] += 1
        for row in rows:
            if not isinstance(row, dict):
                rejection_reasons["row-not-object"] += 1
                continue
            title = clean_text(row.get("title"), 500)
            title_position = raw_text.find(title) if title else -1
            source_url = ""
            for support in supports:
                segment = getattr(support, "segment", None)
                start_index = getattr(segment, "start_index", -1) if segment else -1
                end_index = getattr(segment, "end_index", -1) if segment else -1
                if title_position >= 0 and start_index <= title_position < end_index:
                    indices = list(getattr(support, "grounding_chunk_indices", None) or [])
                    if indices and 0 <= indices[0] < len(urls):
                        source_url = urls[indices[0]]
                        break
            if not source_url:
                citation_index = row.get("citation_index")
                if isinstance(citation_index, int) and 0 <= citation_index < len(urls):
                    source_url = urls[citation_index]
            if not source_url:
                rejection_reasons["missing-grounding-source"] += 1
                continue
            listing_type = clean_text(row.get("listing_type")).lower()
            if listing_type not in {"sold", "active"}:
                rejection_reasons["invalid-listing-type"] += 1
                continue
            try:
                comp = Comparable(
                    source=self.name,
                    title=title,
                    price=parse_money(row.get("price")),
                    shipping=parse_money(row.get("shipping")),
                    listing_type=listing_type,  # type: ignore[arg-type]
                    condition=clean_text(row.get("condition"), 100) or "Unknown",
                    url=source_url,
                    observed_at=datetime.now(timezone.utc).isoformat(),
                    sold_at=clean_text(row.get("sold_at")),
                    match_score=max(0.0, min(1.0, float(row.get("match_score") or 0.6))),
                )
            except (TypeError, ValueError):
                rejection_reasons["invalid-comparable-fields"] += 1
                continue
            if comp.price > 0 and comp.title:
                comps.append(comp)
            else:
                rejection_reasons["missing-title-or-price"] += 1
        if not comps and not supports:
            rejection_reasons["missing-grounding-metadata"] += 1
        deduplicated: dict[tuple[str, float, str], Comparable] = {}
        for comp in comps:
            deduplicated[(comp.url, comp.delivered_price, comp.title.lower())] = comp
        comps = list(deduplicated.values())
        status = "accepted" if comps else "no-usable-evidence"
        self._append_audit({
            "itemId": item.item_id,
            "itemTitle": item.title,
            "itemUrl": item.item_url,
            "model": self.config.market.gemini_model,
            "status": status,
            "startedAt": started_at,
            "completedAt": datetime.now(timezone.utc).isoformat(),
            "responseRowCount": response_row_count or len(rows),
            "acceptedComparables": len(comps),
            "groundingSourceCount": sum(bool(url) for url in urls),
            "groundingSources": [url for url in urls if url][:20],
            "candidateCount": len(candidates),
            "finishReasons": [reason for reason in finish_reasons if reason],
            "rejectionReasons": dict(sorted(rejection_reasons.items())),
            "acceptedEvidence": [
                {
                    **comp.__dict__,
                    "delivered_price": comp.delivered_price,
                }
                for comp in comps
            ],
            "usage": self._usage_metadata(response),
            "responseExcerpt": clean_text(raw_text, 4_000),
        })
        return comps
