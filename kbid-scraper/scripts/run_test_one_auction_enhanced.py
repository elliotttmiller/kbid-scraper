"""Run a single-auction smoke test against ProductionKBidScraper

This script instantiates the enhanced scraper, finds the first auction,
scrapes a single item (max_items=1) and writes JSON output into a
timestamped results directory under `results/` so runs are isolated.
"""
from datetime import datetime
import json
import os
import sys
import uuid

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scraper_enhanced import ProductionKBidScraper


def make_run_dir(base: Path) -> Path:
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    rid = uuid.uuid4().hex[:8]
    run_dir = base / f"run_enhanced_{ts}_{rid}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def main():
    results_base = ROOT / 'results'
    results_base.mkdir(exist_ok=True)
    run_dir = make_run_dir(results_base)

    print(f"Run directory: {run_dir}")

    # Instantiate scraper (headless by default)
    scraper = ProductionKBidScraper(headless=True, rate_limit=1.5)

    print("Fetching auction list (will use first auction for a quick test)...")
    auctions = scraper.scrape_auction_list()
    if not auctions:
        print("No auctions found. Exiting.")
        return 1

    first = auctions[0]
    print(f"Using auction: {first.title} (id={first.auction_id})")

    items = scraper.scrape_auction_items(first.auction_id, max_items=10)
    print(f"Scraped {len(items)} item(s) from auction {first.auction_id}")

    out_file = run_dir / 'items.json'
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump([item.__dict__ for item in items], f, indent=2, ensure_ascii=False, default=str)

    print(f"Wrote output to {out_file}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
