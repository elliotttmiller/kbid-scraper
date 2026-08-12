from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import asdict, replace
from pathlib import Path

from .config import load_config
from .export import write_opportunity_analysis_report, write_results, write_triage_shortlist
from .environment import feature_explicitly_disabled
from .ingestion import load_items
from .pipeline import AnalysisPipeline
from .providers import EbayBrowseProvider, GeminiGroundedResearchProvider, ManualComparableProvider, MarketProvider
from .run_layout import RunLayout, atomic_json_write, cst_log_formatter, cst_now_iso
from .store import EngineStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evidence-backed auction valuation and maximum-bid engine")
    parser.add_argument("input", help="K-Bid scraper CSV")
    parser.add_argument("--output", "-o", default=None,
                        help="Opportunity CSV. Relative names are saved under run/outputs.")
    parser.add_argument("--jsonl", default=None, help="Optional full-fidelity JSONL output including comps and costs")
    parser.add_argument("--config", default="engine_config.json")
    parser.add_argument("--manual-comps", default=None, help="Analyst-verified comparable-sales CSV")
    parser.add_argument("--candidate-csv", default=None,
                        help="Restrict raw input to item URLs in a prior opportunity CSV and import its priority signals")
    parser.add_argument("--ebay", action="store_true", help="Use official eBay Browse active-listing evidence")
    parser.add_argument("--gemini-research", action="store_true",
                        help="Use Gemini triage followed by Google Search-grounded research")
    parser.add_argument("--gemini-triage-only", action="store_true",
                        help="Run non-grounded Flash-Lite opportunity triage without grounded Gemini research")
    parser.add_argument("--resume", action="store_true", help="Skip item/config pairs already checkpointed in SQLite")
    parser.add_argument("--include-closed", action="store_true", help="Include closed or zero-time auction lots")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO")
    parser.add_argument("--results-root", default="results")
    parser.add_argument("--run-name", default="analysis")
    parser.add_argument("--run-dir", default=None, help="Explicit run directory for resume or external orchestration")
    return parser


def _configure_file_logging(layout: RunLayout) -> None:
    root = logging.getLogger()
    formatter = cst_log_formatter("%(asctime)s CST %(levelname)s %(message)s")
    for path, level in ((layout.log_path, logging.INFO), (layout.error_log_path, logging.ERROR)):
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setLevel(level)
        handler.setFormatter(formatter)
        root.addHandler(handler)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    gemini_requested = args.gemini_research or args.gemini_triage_only
    gemini_blocked = gemini_requested and feature_explicitly_disabled("ENABLE_GEMINI_RESEARCH")
    effective_settings = vars(args).copy()
    effective_settings["gemini_research_effective"] = bool(args.gemini_research and not gemini_blocked)
    effective_settings["gemini_triage_effective"] = bool(gemini_requested and not gemini_blocked)
    effective_settings["gemini_research_blocked_by_environment"] = bool(gemini_blocked)
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(asctime)s %(levelname)s %(message)s")
    layout = RunLayout.create(args.results_root, args.run_name, args.run_dir)
    _configure_file_logging(layout)
    output_path = args.output if args.output and os.path.isabs(args.output) else str(layout.artifact("outputs", args.output or "opportunities.csv"))
    jsonl_path = args.jsonl if args.jsonl and os.path.isabs(args.jsonl) else str(layout.artifact("outputs", args.jsonl or "opportunities.jsonl"))
    layout.write_manifest(
        status="starting",
        started_at=cst_now_iso(),
        command=sys.argv if argv is None else ["analyze_auctions.py", *argv],
        settings=effective_settings,
        input_csv=str(Path(args.input).resolve()),
    )
    config = load_config(args.config)
    items, errors = load_items(args.input, include_closed=args.include_closed)
    if args.candidate_csv:
        candidates, candidate_errors = load_items(args.candidate_csv, include_closed=args.include_closed)
        errors.extend(f"candidate CSV: {error}" for error in candidate_errors)
        candidate_by_url = {item.item_url: item for item in candidates if item.item_url}
        selected = []
        for item in items:
            prior = candidate_by_url.get(item.item_url)
            if prior:
                selected.append(replace(
                    item,
                    prior_expected_profit=prior.prior_expected_profit,
                    prior_expected_sell_price=prior.prior_expected_sell_price,
                    prior_expected_roi=prior.prior_expected_roi,
                    prior_maximum_bid=prior.prior_maximum_bid,
                    prior_market_confidence=prior.prior_market_confidence,
                    prior_verified_sold_count=prior.prior_verified_sold_count,
                    prior_active_listing_count=prior.prior_active_listing_count,
                    prior_active_listing_median=prior.prior_active_listing_median,
                ))
        items = selected
        logging.info("Candidate filter selected %d raw lots from %s", len(items), args.candidate_csv)
    for error in errors[:20]:
        logging.warning("Rejected input row: %s", error)
    if len(errors) > 20:
        logging.warning("Suppressed %d additional row errors", len(errors) - 20)
    if not items:
        logging.error("No analyzable open lots found in %s", args.input)
        layout.write_manifest(status="failed", error="No analyzable open lots found")
        return 2

    providers: list[MarketProvider] = []
    gemini_provider = None
    if args.manual_comps:
        providers.append(ManualComparableProvider(args.manual_comps))
    if args.ebay:
        providers.append(EbayBrowseProvider(config))
    if gemini_blocked:
        logging.warning("Gemini research requested but blocked by ENABLE_GEMINI_RESEARCH=false")
    elif gemini_requested:
        gemini_provider = GeminiGroundedResearchProvider(config)
    if not providers:
        logging.warning("No market providers configured; results will be marked RESEARCH or PASS")

    triage_path = layout.artifact("reports", "gemini-triage.json")
    triage_csv_path = layout.artifact("outputs", "opportunities-triaged-top-50.csv")
    grounded_detail_path = layout.artifact("reports", "gemini-grounded-research.jsonl")
    grounded_summary_path = layout.artifact("reports", "gemini-grounded-summary.json")
    grounded_readable_path = layout.artifact("reports", "gemini-grounded-report.md")
    opportunity_report_path = layout.artifact("reports", "opportunity-analysis-report.md")
    store = EngineStore(str(layout.cache_path))
    try:
        layout.write_manifest(status="valuing", counts={"input_items": len(items), "rejected_rows": len(errors)})
        pipeline = AnalysisPipeline(config, providers, store)
        results = pipeline.analyze_items(items, resume=args.resume)
        triage_candidates = []
        if gemini_provider is not None:
            layout.write_manifest(status="triaging", counts={"input_items": len(items)})
            triage_candidates = gemini_provider.prepare_from_results(results)
            atomic_json_write(triage_path, gemini_provider.triage_status)
            write_triage_shortlist(gemini_provider.triage_status, triage_candidates, triage_csv_path)
        if gemini_provider is not None and args.gemini_research:
            layout.write_manifest(status="researching", counts={"grounded_candidates": gemini_provider.selected_item_count})
            results = AnalysisPipeline(config, [*providers, gemini_provider], store).analyze_items(items)
        opportunity_count = write_results(results, output_path, jsonl_path)
    finally:
        store.close()
    summary_path = layout.artifact("reports", "run-summary.json")
    if gemini_provider is not None:
        atomic_json_write(triage_path, gemini_provider.triage_status)
        write_triage_shortlist(gemini_provider.triage_status, triage_candidates, triage_csv_path)
    grounded_summary = None
    if gemini_provider is not None and args.gemini_research:
        grounded_summary = gemini_provider.write_grounded_reports(
            grounded_detail_path, grounded_summary_path, grounded_readable_path
        )
    write_opportunity_analysis_report(
        results,
        gemini_provider.triage_status if gemini_provider is not None else None,
        gemini_provider.audit_records if gemini_provider is not None else None,
        opportunity_report_path,
    )
    final_status = (
        "partial_success"
        if grounded_summary is not None
        and grounded_summary.get("requestsAttempted", 0) > 0
        and grounded_summary.get("acceptedComparables", 0) == 0
        else "completed"
    )
    summary = {
        "run_id": layout.run_id,
        "status": final_status,
        "completed_at": cst_now_iso(),
        "input_items": len(items),
        "rejected_rows": len(errors),
        "analysis_items": len(results),
        "opportunity_items": opportunity_count,
        "gemini_grounded": grounded_summary,
        "artifacts": layout.relative_artifacts({
            "opportunities_csv": output_path,
            "opportunities_jsonl": jsonl_path,
            "run_log": layout.log_path,
            "error_log": layout.error_log_path,
            "engine_config": layout.metadata_dir / "engine-config.json",
            "run_summary": summary_path,
            "opportunity_analysis_report": opportunity_report_path,
            **({
                "gemini_triage": triage_path,
                "gemini_triage_shortlist": triage_csv_path,
            } if gemini_provider is not None else {}),
            **({
                "gemini_grounded_research": grounded_detail_path,
                "gemini_grounded_summary": grounded_summary_path,
                "gemini_grounded_report": grounded_readable_path,
            } if grounded_summary is not None else {}),
        }),
    }
    atomic_json_write(summary_path, summary)
    atomic_json_write(layout.metadata_dir / "engine-config.json", asdict(config))
    layout.write_manifest(status=final_status, completed_at=summary["completed_at"], counts={
        "input_items": len(items), "rejected_rows": len(errors), "analysis_items": len(results),
        "opportunity_items": opportunity_count,
    }, artifacts=summary["artifacts"], gemini_grounded=grounded_summary)
    logging.info("Analyzed %d lots; run directory: %s", len(results), layout.root)
    return 0
