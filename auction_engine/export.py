from __future__ import annotations

import csv
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .models import AnalysisResult


CSV_FIELDS = (
    "time_remaining",
    "item_title",
    "expected_profit",
    "current_bid",
    "expected_sell_price",
    "expected_roi_percent",
    "maximum_bid",
    "lot_closing_time",
    "market_confidence",
    "verified_sold_comp_count",
    "verified_sold_median_price",
    "active_listing_comp_count",
    "ebay_active_listing_count",
    "active_listing_median_price",
    "lot_number",
    "auction_title",
    "category",
    "location",
    "item_url",
    "risk_factors",
    "opportunity_score",
    "risk_score",
    "rank",
    "recommendation",
)


CENTRAL = ZoneInfo("America/Chicago")


def _closing_datetime(result: AnalysisResult) -> datetime | None:
    value = result.item.item_closing_time.strip()
    if value:
        normalized = value.replace(" CDT", "").replace(" CST", "").strip()
        for pattern in ("%a, %b %d, %Y %I:%M%p", "%m/%d/%Y %I:%M %p", "%m/%d/%Y %I:%M%p"):
            try:
                return datetime.strptime(normalized, pattern).replace(tzinfo=CENTRAL)
            except ValueError:
                continue
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=CENTRAL) if parsed.tzinfo is None else parsed.astimezone(CENTRAL)
        except ValueError:
            pass
    if result.item.minutes_until_close is not None:
        analyzed = datetime.fromisoformat(result.analyzed_at.replace("Z", "+00:00"))
        if analyzed.tzinfo is None:
            analyzed = analyzed.replace(tzinfo=timezone.utc)
        from datetime import timedelta
        return analyzed.astimezone(CENTRAL) + timedelta(minutes=result.item.minutes_until_close)
    return None


def _remaining_text(minutes_remaining: float | None) -> str:
    if minutes_remaining is None:
        return "Unknown"
    total_minutes = max(0, int(round(minutes_remaining)))
    if total_minutes == 0:
        return "Closed"
    days, remainder = divmod(total_minutes, 1_440)
    hours, minutes = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if days or hours:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def _evidence_median(result: AnalysisResult, listing_types: set[str]) -> float | None:
    prices = [
        comp.delivered_price
        for comp in result.evidence
        if comp.listing_type in listing_types and comp.delivered_price > 0
    ]
    return round(statistics.median(prices), 2) if prices else None


def _ebay_active_count(result: AnalysisResult) -> int:
    return sum(
        comp.source == "ebay_browse" and comp.listing_type == "active"
        for comp in result.evidence
    )


def flatten_result(result: AnalysisResult, rank: int) -> dict[str, object]:
    closes_at = _closing_datetime(result)
    return {
        "rank": rank,
        "recommendation": result.recommendation,
        "opportunity_score": result.opportunity_score,
        "risk_score": result.risk_score,
        "maximum_bid": result.maximum_bid,
        "lot_closing_time": closes_at.strftime("%a, %b %d, %Y %I:%M %p %Z") if closes_at else "Unknown",
        "time_remaining": _remaining_text(result.item.minutes_until_close),
        "current_bid": result.item.current_bid,
        "expected_sell_price": result.expected_sell_price,
        "expected_profit": result.expected_profit,
        "expected_roi_percent": result.expected_roi,
        "market_confidence": result.market.confidence,
        "verified_sold_comp_count": result.market.sold_count,
        "verified_sold_median_price": _evidence_median(result, {"sold", "manual"}),
        "active_listing_comp_count": result.market.active_count,
        "ebay_active_listing_count": _ebay_active_count(result),
        "active_listing_median_price": _evidence_median(result, {"active"}),
        "lot_number": result.item.lot_number,
        "item_title": result.item.title,
        "auction_title": result.item.auction_title,
        "category": result.item.category,
        "location": result.item.location,
        "item_url": result.item.item_url,
        "risk_factors": " | ".join(result.risk_factors),
    }


def is_opportunity(result: AnalysisResult) -> bool:
    return (
        result.recommendation != "PASS"
        and result.expected_profit > 0
        and result.maximum_bid > result.item.current_bid
    )


def write_triage_shortlist(status: dict[str, object], items: list, path: str | Path) -> int:
    decisions = status.get("decisions")
    if not isinstance(decisions, list):
        selected_ids = status.get("selectedItemIds")
        decisions = [
            {
                "itemId": item_id,
                "selected": True,
                "strategicScore": 0,
                "reason": "Deterministic fallback selection",
            }
            for item_id in selected_ids
        ] if isinstance(selected_ids, list) else []
    item_by_id = {item.item_id: item for item in items}
    selected = sorted(
        (row for row in decisions if isinstance(row, dict) and row.get("selected") is True),
        key=lambda row: float(row.get("strategicScore") or 0),
        reverse=True,
    )
    fields = (
        "time_remaining", "item_title", "expected_profit", "current_bid",
        "expected_sell_price", "expected_roi_percent", "maximum_bid",
        "lot_closing_time", "market_confidence", "verified_sold_comp_count",
        "ebay_active_listing_count", "active_listing_median_price", "lot_number",
        "auction_title", "category", "location", "item_url",
        "triage_strategic_score", "triage_selection_reason", "triage_rank",
    )
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for rank, decision in enumerate(selected, start=1):
            item = item_by_id.get(str(decision.get("itemId")))
            if item is None:
                continue
            writer.writerow({
                "time_remaining": _remaining_text(item.minutes_until_close),
                "item_title": item.title,
                "expected_profit": item.prior_expected_profit,
                "current_bid": item.current_bid,
                "expected_sell_price": item.prior_expected_sell_price,
                "expected_roi_percent": item.prior_expected_roi,
                "maximum_bid": item.prior_maximum_bid,
                "lot_closing_time": item.item_closing_time,
                "market_confidence": item.prior_market_confidence,
                "verified_sold_comp_count": item.prior_verified_sold_count,
                "ebay_active_listing_count": item.prior_active_listing_count,
                "active_listing_median_price": item.prior_active_listing_median,
                "lot_number": item.lot_number,
                "auction_title": item.auction_title,
                "category": item.category,
                "location": item.location,
                "item_url": item.item_url,
                "triage_strategic_score": decision.get("strategicScore"),
                "triage_selection_reason": decision.get("reason"),
                "triage_rank": rank,
            })
    return len(selected)


def write_results(results: list[AnalysisResult], csv_path: str | Path, jsonl_path: str | Path | None = None) -> int:
    ordered_results = sorted(
        results,
        key=lambda result: (
            _closing_datetime(result) is None,
            _closing_datetime(result) or datetime.max.replace(tzinfo=timezone.utc),
            -result.expected_profit,
            -result.market.sold_count,
            -_ebay_active_count(result),
            -result.market.active_count,
            -result.market.confidence,
        ),
    )
    opportunities = [result for result in ordered_results if is_opportunity(result)]
    csv_target = Path(csv_path)
    csv_target.parent.mkdir(parents=True, exist_ok=True)
    with csv_target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for rank, result in enumerate(opportunities, start=1):
            writer.writerow(flatten_result(result, rank))
    if jsonl_path:
        json_target = Path(jsonl_path)
        json_target.parent.mkdir(parents=True, exist_ok=True)
        with json_target.open("w", encoding="utf-8") as handle:
            for result in ordered_results:
                handle.write(json.dumps(result.to_dict(), separators=(",", ":")) + "\n")
    return len(opportunities)


def _md(value: object, limit: int = 500) -> str:
    return str(value or "").strip().replace("|", "\\|").replace("\n", " ")[:limit]


def write_opportunity_analysis_report(
    results: list[AnalysisResult],
    triage_status: dict[str, object] | None,
    grounded_records: list[dict[str, object]] | None,
    path: str | Path,
) -> int:
    opportunities = [result for result in results if is_opportunity(result)]
    opportunities.sort(key=lambda result: (
        _closing_datetime(result) is None,
        _closing_datetime(result) or datetime.max.replace(tzinfo=timezone.utc),
        -result.expected_profit,
    ))
    decisions = {
        str(row.get("itemId")): row
        for row in (triage_status or {}).get("decisions", [])
        if isinstance(row, dict)
    }
    audits = {
        str(row.get("itemId")): row
        for row in (grounded_records or [])
        if isinstance(row, dict)
    }
    profits = [result.expected_profit for result in opportunities]
    rois = [result.expected_roi for result in opportunities]
    confidences = [result.market.confidence for result in opportunities]
    verified = sum(result.market.sold_count > 0 for result in opportunities)
    ebay_covered = sum(_ebay_active_count(result) > 0 for result in opportunities)
    def gemini_evidence(result: AnalysisResult) -> list:
        return [comp for comp in result.evidence if comp.source == "gemini_grounded"]

    grounded = sum(bool(gemini_evidence(result)) for result in opportunities)
    researched = sum(result.item.item_id in audits for result in opportunities)
    recommendation_counts: dict[str, int] = {}
    for result in opportunities:
        recommendation_counts[result.recommendation] = recommendation_counts.get(result.recommendation, 0) + 1
    median_profit = statistics.median(profits) if profits else 0
    median_roi = statistics.median(rois) if rois else 0
    median_confidence = statistics.median(confidences) if confidences else 0
    within_24 = sum(result.item.minutes_until_close is not None and result.item.minutes_until_close <= 1_440 for result in opportunities)
    total_modeled_profit = sum(profits)

    lines = [
        "# Auction Opportunity Analysis Report",
        "",
        "## Executive Summary",
        "",
        f"- Viable opportunity targets: **{len(opportunities)}**",
        f"- Modeled expected profit across all targets: **${total_modeled_profit:,.2f}**",
        f"- Median expected profit per target: **${median_profit:,.2f}**",
        f"- Median expected ROI: **{median_roi:,.1f}%**",
        f"- Median market confidence: **{median_confidence:.1%}**",
        f"- Closing within 24 hours at analysis time: **{within_24}**",
        f"- Targets with verified sold evidence: **{verified}/{len(opportunities)}**",
        f"- Targets with eBay active-listing evidence: **{ebay_covered}/{len(opportunities)}**",
        f"- Grounded requests from this run covering final targets: **{researched}/{len(opportunities)}**",
        f"- Final targets with grounded Gemini evidence, including cache reuse: **{grounded}/{len(opportunities)}**",
        f"- Recommendations: **{', '.join(f'{name} {count}' for name, count in sorted(recommendation_counts.items())) or 'None'}**",
        "",
        "> Expected profit and ROI are modeled estimates, not guaranteed portfolio returns. Active eBay listings are asking prices, not completed sales. Targets without verified sold evidence require manual validation before bidding.",
        "",
        "## Ranked Targets",
        "",
        "Rows are ordered by closing urgency, then expected profit. `Not selected` means the deterministic opportunity remained valid but did not receive grounded Gemini research.",
        "",
        "| # | Time left | Target | Rec. | Bid | Expected sale | Expected profit | ROI | Max bid | Confidence | Sold comps | eBay active | Gemini comps | Research |",
        "|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for rank, result in enumerate(opportunities, start=1):
        audit = audits.get(result.item.item_id) or {}
        decision = decisions.get(result.item.item_id) or {}
        retained_gemini = gemini_evidence(result)
        evidence_count = len(retained_gemini)
        if result.item.item_id in audits:
            research = "Accepted" if evidence_count else "No usable evidence"
        elif evidence_count:
            research = "Cached evidence"
        elif decision.get("selected") is True:
            research = "Selected; no request record"
        else:
            research = "Not selected"
        title = f"[{_md(result.item.title)}]({result.item.item_url})" if result.item.item_url else _md(result.item.title)
        lines.append(
            f"| {rank} | {_remaining_text(result.item.minutes_until_close)} | {title} | {result.recommendation} "
            f"| ${result.item.current_bid:,.2f} | ${result.expected_sell_price:,.2f} | ${result.expected_profit:,.2f} "
            f"| {result.expected_roi:,.1f}% | ${result.maximum_bid:,.2f} | {result.market.confidence:.1%} "
            f"| {result.market.sold_count} | {_ebay_active_count(result)} | {evidence_count} | {research} |"
        )

    lines.extend(["", "## Grounded Research Detail", ""])
    researched_results = [
        result for result in opportunities
        if result.item.item_id in audits or gemini_evidence(result)
    ]
    for index, result in enumerate(researched_results, start=1):
        audit = audits.get(result.item.item_id) or {}
        decision = decisions.get(result.item.item_id) or {}
        lines.extend([
            f"### {index}. {_md(result.item.title)}",
            "",
            f"- Auction lot: [{_md(result.item.item_url)}]({result.item.item_url})",
            f"- Recommendation: **{result.recommendation}**",
            f"- Current bid / maximum bid: **${result.item.current_bid:,.2f} / ${result.maximum_bid:,.2f}**",
            f"- Expected sale / profit / ROI: **${result.expected_sell_price:,.2f} / ${result.expected_profit:,.2f} / {result.expected_roi:,.1f}%**",
            f"- Opportunity / risk score: **{result.opportunity_score:.1f} / {result.risk_score:.1f}**",
            f"- Market confidence: **{result.market.confidence:.1%}**",
            f"- Evidence: **{result.market.sold_count} sold, {_ebay_active_count(result)} eBay active, {len(gemini_evidence(result))} Gemini grounded**",
            f"- Gemini triage score: **{float(decision.get('strategicScore') or 0):.1f}** - {_md(decision.get('reason') or 'No triage explanation')}",
            f"- Risk factors: {_md(' | '.join(result.risk_factors) or 'None recorded', 1_500)}",
            "",
        ])
        evidence = audit.get("acceptedEvidence") or [
            {**comp.__dict__, "delivered_price": comp.delivered_price}
            for comp in gemini_evidence(result)
        ]
        if evidence:
            lines.extend([
                "| Type | Comparable | Delivered price | Condition | Sold date | Source |",
                "|---|---|---:|---|---|---|",
            ])
            for comp in evidence:
                url = comp.get("url") or ""
                source = f"[Open source]({url})" if url else "Unavailable"
                lines.append(
                    f"| {_md(comp.get('listing_type'))} | {_md(comp.get('title'))} "
                    f"| ${float(comp.get('delivered_price') or 0):,.2f} | {_md(comp.get('condition'))} "
                    f"| {_md(comp.get('sold_at')) or '-'} | {source} |"
                )
            lines.append("")
        else:
            rejections = audit.get("rejectionReasons") or {}
            reason = ", ".join(f"{name}: {count}" for name, count in sorted(rejections.items())) or "No cited priced result found"
            lines.extend([f"Grounded research returned no accepted evidence. Reason: {_md(reason)}", ""])

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    temp.replace(target)
    return len(opportunities)
