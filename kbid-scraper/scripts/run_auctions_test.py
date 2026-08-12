"""
Run full scrape of the first N auctions discovered on K-Bid

This script will:
- Discover auction listing pages
- Collect the first N unique auctions
- Scrape every item for each auction (no per-item limit)
- Optionally filter items by time remaining on the auction timer
- Save combined results to CSV in the scraper's run directory

Usage (PowerShell):
  # Test run — 3 auctions, items closing within 48 hours, at least 1 hour left
  python .\scripts\run_auctions_test.py --num-auctions 3 --delay 1.5 --output test_auctions.csv --max-hours 48 --min-hours 1

  # All items regardless of closing time
  python .\scripts\run_auctions_test.py --num-auctions 5 --delay 1.5 --output test_auctions.csv

Notes:
- This uses KBidScraperFixed from `scraper_enhanced.py` in the parent folder.
- --max-hours: keep only items closing within this many hours (e.g. 48 = closing in 2 days or less)
- --min-hours: drop items closing sooner than this many hours (avoids items already too close to end)
"""

import argparse
import json
import logging
import sys
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Ensure local package import
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
WORKSPACE_ROOT = os.path.abspath(os.path.join(PROJECT_ROOT, '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

import scraper_enhanced as se
from auction_engine.run_layout import RunLayout, atomic_json_write, cst_log_formatter, cst_now_iso
from auction_engine.environment import feature_explicitly_disabled

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def configure_run_logging(layout):
    root_logger = logging.getLogger()
    formatter = cst_log_formatter('%(asctime)s CST - %(levelname)s - %(message)s')
    existing = {getattr(handler, 'baseFilename', None) for handler in root_logger.handlers}
    for path, level in ((layout.log_path, logging.INFO), (layout.error_log_path, logging.ERROR)):
        resolved = os.path.abspath(path)
        if resolved in existing:
            continue
        handler = logging.FileHandler(resolved, encoding='utf-8')
        handler.setLevel(level)
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)


def merge_csv_values(*values):
    merged = []
    seen = set()
    for value in values:
        if not value:
            continue
        if isinstance(value, list):
            parts = value
        else:
            parts = str(value).replace(';', ',').split(',')
        for part in parts:
            item = str(part).strip()
            if item and item not in seen:
                seen.add(item)
                merged.append(item)
    return ','.join(merged) if merged else None


def load_category_profile(profile_name):
    if not profile_name:
        return {}
    profile_path = os.path.join(PROJECT_ROOT, 'category_profiles.json')
    with open(profile_path, 'r', encoding='utf-8') as fh:
        profiles = json.load(fh)
    if profile_name not in profiles:
        raise ValueError(f"Unknown category profile '{profile_name}'. Available: {', '.join(sorted(profiles))}")
    return profiles[profile_name]


def normalize_auction_url(value):
    match = re.search(r'https?://www\.k-bid\.com/auction/\d+(?:[^\s,\]\)]*)?', str(value or ''))
    if match:
        return match.group(0).rstrip(').]')
    match = re.search(r'/auction/\d+(?:[^\s,\]\)]*)?', str(value or ''))
    return f"https://www.k-bid.com{match.group(0).rstrip(').]')}" if match else None


def load_urls_file(path):
    urls, seen = [], set()
    with open(path, 'r', encoding='utf-8-sig') as fh:
        content = fh.read()
    for match in re.finditer(r'https?://www\.k-bid\.com/auction/\d+(?:[^\s,\]\)]*)?', content):
        url = normalize_auction_url(match.group(0))
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def chunked(values, size):
    for index in range(0, len(values), size):
        yield index // size + 1, values[index:index + size]


def load_checkpoint(path):
    if not path or not os.path.exists(path):
        return {'completed': {}, 'failed': {}, 'started_at': cst_now_iso()}
    with open(path, 'r', encoding='utf-8') as fh:
        data = json.load(fh)
    data.setdefault('completed', {})
    data.setdefault('failed', {})
    return data


def save_checkpoint(path, checkpoint):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    checkpoint['updated_at'] = cst_now_iso()
    tmp_path = f"{path}.tmp"
    with open(tmp_path, 'w', encoding='utf-8') as fh:
        json.dump(checkpoint, fh, indent=2, sort_keys=True)
    os.replace(tmp_path, path)


def apply_time_filter(items, min_hours, max_hours):
    """Filter items by minutes_until_close.

    Keeps items where minutes_until_close is a number and falls within
    [min_hours * 60, max_hours * 60].  Items with 'N/A' (unknown close
    time) are always kept so we don't silently discard valid lots.
    """
    if min_hours is None and max_hours is None:
        return items, 0

    kept, dropped = [], 0
    min_minutes = min_hours * 60 if min_hours is not None else None
    max_minutes = max_hours * 60 if max_hours is not None else None

    for item in items:
        mins = item.get('minutes_until_close', 'N/A')
        if mins == 'N/A':
            kept.append(item)  # unknown — keep to avoid data loss
            continue
        if min_minutes is not None and mins < min_minutes:
            dropped += 1
            continue
        if max_minutes is not None and mins > max_minutes:
            dropped += 1
            continue
        kept.append(item)

    return kept, dropped


def main():
    parser = argparse.ArgumentParser(description='Scrape first N auctions fully and save combined CSV')
    parser.add_argument('--num-auctions', '-n', type=int, default=5, help='Number of auctions to scrape (default: 5)')
    parser.add_argument('--all-auctions', action='store_true',
                        help='Scrape every discovered auction that passes listing filters; ignores --num-auctions.')
    parser.add_argument('--auction-url', action='append', default=None,
                        help='Scrape specific auction URL(s) and skip auction discovery. Repeat this option for multiple auctions.')
    parser.add_argument('--urls-file', default=None,
                        help='Text file containing auction URLs. Skips auction discovery.')
    parser.add_argument('--chunk-size', type=int, default=10,
                        help='Number of auctions to process per checkpoint chunk (default: 10).')
    parser.add_argument('--checkpoint', default=None,
                        help='Checkpoint JSON path. Default: run/state/scrape-checkpoint.json.')
    parser.add_argument('--resume', action='store_true',
                        help='Resume using --run-dir or an explicit --checkpoint and append to the existing raw CSV.')
    parser.add_argument('--delay', '-d', type=float, default=1.5, help='Delay between requests in seconds (default: 1.5)')
    parser.add_argument('--item-workers', type=int, default=8,
                        help='Concurrent item detail fetch workers per auction (default: 8)')
    parser.add_argument('--page-workers', type=int, default=4,
                        help='Concurrent auction pagination pages per auction (default: 4)')
    parser.add_argument('--auction-workers', type=int, default=1,
                        help='Concurrent auctions to scrape (default: 1)')
    parser.add_argument('--output', '-o', default='lots.csv',
                        help='Raw lot CSV filename. Relative names are saved under run/raw (default: lots.csv).')
    parser.add_argument('--results-root', default=os.path.join(WORKSPACE_ROOT, 'results'),
                        help='Root directory containing runs, shared cache, and latest.json.')
    parser.add_argument('--run-name', default=None,
                        help='Short human-readable label recorded in run metadata.')
    parser.add_argument('--run-dir', default=None,
                        help='Use an explicit run directory, primarily for resuming an existing run.')
    parser.add_argument('--max-hours', type=float, default=None,
                        help='Only keep items closing within this many hours (e.g. 48). Default: no limit.')
    parser.add_argument('--min-hours', type=float, default=None,
                        help='Drop items closing sooner than this many hours (e.g. 1). Default: no limit.')
    parser.add_argument('--listing-max-hours', type=float, default=None,
                        help='Only discover auction listings whose countdown is within this many hours.')
    parser.add_argument('--listing-min-hours', type=float, default=None,
                        help='Skip auction listings whose countdown is sooner than this many hours.')
    parser.add_argument('--origin-zip', default=None,
                        help='ZIP code to use with K-Bid distance filtering.')
    parser.add_argument('--radius-miles', type=int, choices=[10, 25, 50, 75, 100, 150, 250], default=None,
                        help='Only discover auctions within this many miles of --origin-zip. Omit for Any.')
    parser.add_argument('--closing-date', default=None,
                        help='Use K-Bid Closing Date filter. Accepts YYYY-MM-DD or MM/DD/YYYY.')
    parser.add_argument('--include-category-ids', default=None,
                        help='Comma-separated K-Bid category_ids to include, e.g. 17,23,24,45,46.')
    parser.add_argument('--exclude-category-ids', default=None,
                        help='Comma-separated K-Bid category_ids to exclude.')
    parser.add_argument('--exclude-lot-terms', default=None,
                        help='Comma-separated whole words or phrases to exclude from lot titles/categories.')
    parser.add_argument('--auction-category-ids', default=None,
                        help='Comma-separated top-level auction_categories[] IDs from K-Bid filter panel.')
    parser.add_argument('--filter-listing-categories', action='store_true',
                        help='Apply category filters at auction-listing discovery. Default: category filters apply only to lots/items.')
    parser.add_argument('--category-profile', default=None,
                        help='Named profile from category_profiles.json, e.g. flip-goldmine.')
    parser.add_argument('--analyze', action='store_true',
                        help='Run the canonical valuation engine after scraping completes.')
    parser.add_argument('--analysis-output', default=None,
                        help='Opportunity CSV filename. Relative names are saved under run/outputs.')
    parser.add_argument('--manual-comps', default=None,
                        help='Optional analyst-verified comparable-sales CSV for valuation.')
    parser.add_argument('--ebay-research', action='store_true',
                        help='Use official eBay Browse active-listing evidence (requires EBAY_CLIENT_ID/SECRET).')
    parser.add_argument('--gemini-research', action='store_true',
                        help='Use Gemini triage followed by grounded research when sold comps are missing.')
    parser.add_argument('--gemini-triage-only', action='store_true',
                        help='After eBay valuation, run non-grounded Flash-Lite triage only; no grounded Gemini calls.')

    args = parser.parse_args()
    gemini_requested = args.gemini_research or args.gemini_triage_only
    gemini_blocked = gemini_requested and feature_explicitly_disabled('ENABLE_GEMINI_RESEARCH')
    effective_settings = vars(args).copy()
    effective_settings['gemini_research_effective'] = bool(args.gemini_research and not gemini_blocked)
    effective_settings['gemini_triage_effective'] = bool(gemini_requested and not gemini_blocked)
    effective_settings['gemini_research_blocked_by_environment'] = bool(gemini_blocked)
    if args.radius_miles is not None and not args.origin_zip:
        parser.error('--origin-zip is required when --radius-miles is set')
    if args.chunk_size < 1:
        parser.error('--chunk-size must be at least 1')
    if args.page_workers < 1:
        parser.error('--page-workers must be at least 1')
    if args.resume and not args.checkpoint and not args.run_dir:
        parser.error('--checkpoint or --run-dir is required when --resume is set')
    try:
        category_profile = load_category_profile(args.category_profile)
    except ValueError as e:
        parser.error(str(e))

    include_category_ids = merge_csv_values(category_profile.get('include_category_ids'), args.include_category_ids)
    exclude_category_ids = merge_csv_values(category_profile.get('exclude_category_ids'), args.exclude_category_ids)
    exclude_lot_terms = merge_csv_values(category_profile.get('exclude_lot_terms'), args.exclude_lot_terms)
    auction_category_ids = merge_csv_values(category_profile.get('auction_category_ids'), args.auction_category_ids)

    inferred_run_dir = args.run_dir
    if args.resume and not inferred_run_dir and args.checkpoint:
        checkpoint_candidate = os.path.abspath(args.checkpoint)
        checkpoint_parent = os.path.dirname(checkpoint_candidate)
        inferred_run_dir = os.path.dirname(checkpoint_parent) if os.path.basename(checkpoint_parent) == 'state' else checkpoint_parent
    run_label = args.run_name or args.category_profile or ('custom-urls' if args.urls_file or args.auction_url else 'kbid-discovery')
    layout = RunLayout.create(args.results_root, run_label, inferred_run_dir)
    configure_run_logging(layout)
    layout.write_manifest(
        status='starting',
        started_at=cst_now_iso(),
        command=sys.argv,
        settings=effective_settings,
    )

    logger.info('Starting multi-auction full scrape')
    scraper = se.KBidScraperFixed(
        delay=args.delay,
        item_workers=args.item_workers,
        page_workers=args.page_workers,
        auction_workers=args.auction_workers,
        origin_zip=args.origin_zip,
        radius_miles=args.radius_miles,
        closing_date=args.closing_date,
        include_category_ids=include_category_ids,
        exclude_category_ids=exclude_category_ids,
        exclude_lot_terms=exclude_lot_terms,
        auction_category_ids=auction_category_ids,
        filter_listing_categories=args.filter_listing_categories,
        listing_max_hours=args.listing_max_hours,
        listing_min_hours=args.listing_min_hours,
        results_root=args.results_root,
        run_dir=str(layout.root),
        run_id=layout.run_id,
    )

    auctions = []
    if args.urls_file:
        auctions = load_urls_file(args.urls_file)
    elif args.auction_url:
        for auction_url_arg in args.auction_url:
            for auction_url in str(auction_url_arg).replace(',', ' ').split():
                normalized_url = normalize_auction_url(auction_url)
                if normalized_url and normalized_url not in auctions:
                    auctions.append(normalized_url)
    else:
        # Discover auctions
        list_pages = scraper.get_auction_list_pages()
        if not list_pages:
            logger.error('No listing pages discovered, exiting.')
            layout.write_manifest(status='failed', error='No listing pages discovered')
            sys.exit(1)

        candidates = {}
        for page in list_pages:
            for auction_url, countdown_seconds in scraper.get_auction_candidates_from_page(page):
                current = candidates.get(auction_url)
                if current is None or (countdown_seconds is not None and countdown_seconds < current):
                    candidates[auction_url] = countdown_seconds
        ordered_candidates = sorted(
            candidates.items(),
            key=lambda entry: (entry[1] is None, entry[1] if entry[1] is not None else float('inf'), entry[0]),
        )
        selected_candidates = ordered_candidates if args.all_auctions else ordered_candidates[:args.num_auctions]
        auctions = [auction_url for auction_url, _ in selected_candidates]
        for position, (auction_url, countdown_seconds) in enumerate(selected_candidates, start=1):
            remaining = f'{countdown_seconds / 3600:.2f}h' if countdown_seconds is not None else 'unknown'
            logger.info(f'  Selected auction {position}/{len(auctions)} by closing time: {auction_url} ({remaining} remaining)')

    if not auctions:
        logger.error('No auctions found to scrape. Exiting.')
        layout.write_manifest(status='failed', error='No auctions found to scrape')
        sys.exit(1)

    logger.info(f'Collected {len(auctions)} auctions to scrape')

    # Scrape each auction fully (no per-item limit)
    total_items = 0
    # Prepare output CSV for streaming: write header once, then append rows per auction
    out_path = args.output if os.path.isabs(args.output) else str(layout.artifact('raw', args.output))
    checkpoint_path = args.checkpoint
    if checkpoint_path:
        checkpoint_path = checkpoint_path if os.path.isabs(checkpoint_path) else str(layout.artifact('state', checkpoint_path))
    else:
        checkpoint_path = str(layout.checkpoint_path)
    checkpoint = load_checkpoint(checkpoint_path) if args.resume else {
        'completed': {},
        'failed': {},
        'started_at': cst_now_iso()
    }
    auctions = [auction for auction in auctions if auction not in checkpoint['completed']]
    logger.info(f'Pending auctions after checkpoint filter: {len(auctions)}')
    csv_headers = [
        'lot_number', 'auction_title', 'item_title', 'short_description',
        'current_bid', 'next_required_bid', 'high_bidder',
        'buyers_premium_rate', 'buyers_premium_cap', 'sales_tax_rate',
        'category', 'category_ids',
        'item_closing_time', 'minutes_until_close', 'closing_status',
        'closing_date', 'item_url',
        'auction_id', 'auction_url', 'location', 'image_url'
    ]

    # Create/overwrite output file and write header
    try:
        os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
        write_header = not (args.resume and os.path.exists(out_path) and os.path.getsize(out_path) > 0)
        with open(out_path, 'a' if args.resume else 'w', newline='', encoding='utf-8') as fh:
            import csv as _csv
            writer = _csv.DictWriter(fh, fieldnames=csv_headers, extrasaction='ignore')
            if write_header:
                writer.writeheader()
        logger.info(f'Initialized streaming CSV: {out_path}')
    except Exception as e:
        logger.error(f'Failed to initialize output CSV {out_path}: {e}')
        layout.write_manifest(status='failed', error=f'Failed to initialize output CSV: {e}')
        raise

    def handle_items(items):
        nonlocal total_items
        if items:
            # Apply time filter before writing
            items, dropped = apply_time_filter(items, args.min_hours, args.max_hours)
            if dropped:
                logger.info(f'  Time filter dropped {dropped} items (outside [{args.min_hours}h – {args.max_hours}h] window)')

            total_items += len(items)

            # Append scraped items to CSV immediately
            try:
                with open(out_path, 'a', newline='', encoding='utf-8') as fh:
                    import csv as _csv
                    writer = _csv.DictWriter(fh, fieldnames=csv_headers, extrasaction='ignore')
                    writer.writerows(items)
                logger.info(f'  Appended {len(items)} items to {out_path}')
            except Exception as e:
                logger.error(f'  Failed to append items to CSV: {e}')

    def process_completed_auction(auction_url, items, started_at):
        before = total_items
        handle_items(items)
        written = total_items - before
        checkpoint['completed'][auction_url] = {
            'items_written': written,
            'duration_seconds': round(time.time() - started_at, 2),
            'completed_at': cst_now_iso()
        }
        checkpoint['failed'].pop(auction_url, None)
        save_checkpoint(checkpoint_path, checkpoint)

    total_chunks = (len(auctions) + args.chunk_size - 1) // args.chunk_size
    for chunk_number, chunk_urls in chunked(auctions, args.chunk_size):
        logger.info(f'Processing chunk {chunk_number}/{total_chunks} ({len(chunk_urls)} auctions)')
        if args.auction_workers <= 1:
            for i, auction_url in enumerate(chunk_urls, 1):
                logger.info(f'[{i}/{len(chunk_urls)}] Scraping auction: {auction_url}')
                started_at = time.time()
                try:
                    items = scraper.scrape_auction_items(auction_url)  # no max_items
                    process_completed_auction(auction_url, items, started_at)
                except Exception as e:
                    logger.error(f'Failed auction {auction_url}: {e}')
                    checkpoint['failed'][auction_url] = {
                        'error': str(e),
                        'failed_at': cst_now_iso()
                    }
                    save_checkpoint(checkpoint_path, checkpoint)
                    scraper.increment_stat('errors')
                time.sleep(args.delay)
        else:
            max_workers = min(args.auction_workers, len(chunk_urls))
            logger.info(f'Scraping auctions with {max_workers} auction workers')
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_meta = {
                    executor.submit(scraper.scrape_auction_items, auction_url): (auction_url, time.time())
                    for auction_url in chunk_urls
                }
                for i, future in enumerate(as_completed(future_to_meta), 1):
                    auction_url, started_at = future_to_meta[future]
                    try:
                        items = future.result()
                    except Exception as e:
                        logger.error(f'[{i}/{len(chunk_urls)}] Failed auction {auction_url}: {e}')
                        checkpoint['failed'][auction_url] = {
                            'error': str(e),
                            'failed_at': cst_now_iso()
                        }
                        save_checkpoint(checkpoint_path, checkpoint)
                        scraper.increment_stat('errors')
                        continue
                    logger.info(f'[{i}/{len(chunk_urls)}] Finished auction: {auction_url}')
                    process_completed_auction(auction_url, items, started_at)
        if chunk_number < total_chunks and args.delay > 0:
            time.sleep(args.delay)

    logger.info('Multi-auction full scrape complete')
    logger.info(f'Auctions scraped: {len(auctions)}')
    logger.info(f'Total items scraped: {total_items}')
    logger.info(f'Output CSV: {out_path}')
    logger.info(f'Checkpoint: {checkpoint_path}')
    logger.info(f'Run directory: {layout.root}')

    if args.analyze:
        if WORKSPACE_ROOT not in sys.path:
            sys.path.insert(0, WORKSPACE_ROOT)
        from auction_engine.config import load_config
        from auction_engine.export import write_opportunity_analysis_report, write_results, write_triage_shortlist
        from auction_engine.ingestion import load_items
        from auction_engine.pipeline import AnalysisPipeline
        from auction_engine.providers import EbayBrowseProvider, GeminiGroundedResearchProvider, ManualComparableProvider
        from auction_engine.store import EngineStore

        engine_config = load_config(os.path.join(WORKSPACE_ROOT, 'engine_config.json'))
        from dataclasses import asdict
        atomic_json_write(layout.metadata_dir / 'engine-config.json', asdict(engine_config))
        analysis_items, row_errors = load_items(out_path)
        for row_error in row_errors[:20]:
            logger.warning(f'Analysis rejected input row: {row_error}')
        providers = []
        gemini_provider = None
        if args.manual_comps:
            providers.append(ManualComparableProvider(args.manual_comps))
        if args.ebay_research:
            providers.append(EbayBrowseProvider(engine_config))
        if gemini_blocked:
            logger.warning('Gemini research requested but blocked by ENABLE_GEMINI_RESEARCH=false')
        elif gemini_requested:
            gemini_provider = GeminiGroundedResearchProvider(engine_config)
        analysis_output = (
            args.analysis_output
            if args.analysis_output and os.path.isabs(args.analysis_output)
            else str(layout.artifact('outputs', args.analysis_output or 'opportunities.csv'))
        )
        analysis_jsonl = str(Path(analysis_output).with_suffix('.jsonl'))
        layout.write_manifest(
            status='valuing',
            counts={
                'auctions_selected': len(auctions),
                'items_written': total_items,
                'analysis_items_pending': len(analysis_items),
            },
        )
        engine_store = EngineStore(str(layout.cache_path))
        try:
            analysis_results = AnalysisPipeline(engine_config, providers, engine_store).analyze_items(analysis_items)
            enriched_candidates = []
            if gemini_provider is not None:
                layout.write_manifest(status='triaging', counts={'analysis_items': len(analysis_results)})
                enriched_candidates = gemini_provider.prepare_from_results(analysis_results)
                atomic_json_write(layout.artifact('reports', 'gemini-triage.json'), gemini_provider.triage_status)
                write_triage_shortlist(
                    gemini_provider.triage_status,
                    enriched_candidates,
                    layout.artifact('outputs', 'opportunities-triaged-top-50.csv'),
                )
            if gemini_provider is not None and args.gemini_research:
                layout.write_manifest(
                    status='researching',
                    counts={'grounded_candidates': gemini_provider.selected_item_count},
                )
                analysis_results = AnalysisPipeline(
                    engine_config, [*providers, gemini_provider], engine_store
                ).analyze_items(analysis_items)
            opportunity_count = write_results(analysis_results, analysis_output, analysis_jsonl)
        finally:
            engine_store.close()
        logger.info(
            f'Valuation complete: {len(analysis_results)} lots analyzed, '
            f'{opportunity_count} viable candidates -> {analysis_output}'
        )
        if gemini_provider is not None:
            atomic_json_write(layout.artifact('reports', 'gemini-triage.json'), gemini_provider.triage_status)
            write_triage_shortlist(
                gemini_provider.triage_status,
                enriched_candidates if args.gemini_triage_only else analysis_items,
                layout.artifact('outputs', 'opportunities-triaged-top-50.csv'),
            )

    grounded_summary = None
    grounded_detail_path = layout.artifact('reports', 'gemini-grounded-research.jsonl')
    grounded_summary_path = layout.artifact('reports', 'gemini-grounded-summary.json')
    grounded_readable_path = layout.artifact('reports', 'gemini-grounded-report.md')
    opportunity_report_path = layout.artifact('reports', 'opportunity-analysis-report.md')
    if args.analyze and gemini_provider is not None and args.gemini_research:
        grounded_summary = gemini_provider.write_grounded_reports(
            grounded_detail_path, grounded_summary_path, grounded_readable_path
        )
    if args.analyze:
        write_opportunity_analysis_report(
            analysis_results,
            gemini_provider.triage_status if gemini_provider is not None else None,
            gemini_provider.audit_records if gemini_provider is not None else None,
            opportunity_report_path,
        )
    final_status = (
        'partial_success'
        if grounded_summary is not None
        and grounded_summary.get('requestsAttempted', 0) > 0
        and grounded_summary.get('acceptedComparables', 0) == 0
        else 'completed'
    )

    artifacts = {
        'raw_lots_csv': out_path,
        'scrape_checkpoint': checkpoint_path,
        'run_log': layout.log_path,
        'error_log': layout.error_log_path,
    }
    if args.analyze:
        artifacts.update({
            'opportunities_csv': analysis_output,
            'opportunities_jsonl': analysis_jsonl,
            'engine_config': layout.metadata_dir / 'engine-config.json',
            'opportunity_analysis_report': opportunity_report_path,
        })
        if gemini_provider is not None:
            artifacts['gemini_triage'] = layout.artifact('reports', 'gemini-triage.json')
            artifacts['gemini_triage_shortlist'] = layout.artifact('outputs', 'opportunities-triaged-top-50.csv')
        if grounded_summary is not None:
            artifacts['gemini_grounded_research'] = grounded_detail_path
            artifacts['gemini_grounded_summary'] = grounded_summary_path
            artifacts['gemini_grounded_report'] = grounded_readable_path
    summary = {
        'run_id': layout.run_id,
        'status': final_status,
        'completed_at': cst_now_iso(),
        'auctions_selected': len(auctions),
        'items_written': total_items,
        'completed_auctions': len(checkpoint.get('completed', {})),
        'failed_auctions': len(checkpoint.get('failed', {})),
        'analysis_items': len(analysis_results) if args.analyze else 0,
        'opportunity_items': opportunity_count if args.analyze else 0,
        'gemini_grounded': grounded_summary,
        'artifacts': layout.relative_artifacts(artifacts),
    }
    summary_path = layout.artifact('reports', 'run-summary.json')
    artifacts['run_summary'] = summary_path
    summary['artifacts'] = layout.relative_artifacts(artifacts)
    atomic_json_write(summary_path, summary)
    layout.write_manifest(
        status=final_status,
        completed_at=summary['completed_at'],
        counts={key: summary[key] for key in ('auctions_selected', 'items_written', 'completed_auctions', 'failed_auctions', 'analysis_items', 'opportunity_items')},
        artifacts=layout.relative_artifacts(artifacts),
        gemini_grounded=grounded_summary,
    )
    logger.info(f'Run manifest: {layout.manifest_path}')


if __name__ == '__main__':
    main()
