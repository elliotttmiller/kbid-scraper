"""
Run full scrape of the first N auctions discovered on K-Bid

This script will:
- Discover auction listing pages
- Collect the first 5 unique auctions
- Scrape every item for each auction (no per-item limit)
- Save combined results to CSV in the scraper's run directory

Usage (PowerShell):
  python .\kbid-scraper\scripts\run_auctions_test.py --num-auctions 5 --delay 1 --output test_auctions.csv

Notes:
- This uses KBidScraperFixed from `scraper_enhanced.py` in the same folder.
"""

import argparse
import logging
import sys
import os
import time

# Ensure local package import
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import scraper_enhanced as se

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description='Scrape first N auctions fully and save combined CSV')
    parser.add_argument('--num-auctions', '-n', type=int, default=5, help='Number of auctions to scrape (default: 5)')
    parser.add_argument('--delay', '-d', type=float, default=1.0, help='Delay between requests in seconds (default: 1.0)')
    parser.add_argument('--output', '-o', default='test_auctions_full.csv', help='Output CSV filename (saved in run dir)')

    args = parser.parse_args()

    logger.info('Starting multi-auction full scrape')
    scraper = se.KBidScraperFixed(delay=args.delay)

    # Discover auctions
    list_pages = scraper.get_auction_list_pages()
    if not list_pages:
        logger.error('No listing pages discovered, exiting.')
        sys.exit(1)

    auctions = []
    for page in list_pages:
        page_auctions = scraper.get_auctions_from_page(page)
        for a in page_auctions:
            if a not in auctions:
                auctions.append(a)
            if len(auctions) >= args.num_auctions:
                break
        if len(auctions) >= args.num_auctions:
            break

    if not auctions:
        logger.error('No auctions found to scrape. Exiting.')
        sys.exit(1)

    logger.info(f'Collected {len(auctions)} auctions to scrape')

    # Scrape each auction fully (no per-item limit)
    total_items = 0
    # Prepare output CSV for streaming: write header once, then append rows per auction
    out_path = os.path.join(scraper.run_dir, args.output)
    csv_headers = [
        'lot_number', 'auction_title', 'item_title', 'short_description',
        'current_bid', 'next_required_bid', 'high_bidder',
        'item_closing_time', 'closing_date', 'item_url',
        'auction_id', 'auction_url', 'location'
    ]

    # Create/overwrite output file and write header
    try:
        with open(out_path, 'w', newline='', encoding='utf-8') as fh:
            import csv as _csv
            writer = _csv.DictWriter(fh, fieldnames=csv_headers, extrasaction='ignore')
            writer.writeheader()
        logger.info(f'Initialized streaming CSV: {out_path}')
    except Exception as e:
        logger.error(f'Failed to initialize output CSV {out_path}: {e}')
        out_path = args.output

    for i, auction_url in enumerate(auctions, 1):
        logger.info(f'[{i}/{len(auctions)}] Scraping auction: {auction_url}')
        items = scraper.scrape_auction_items(auction_url)  # no max_items
        # Extend internal store
        if items:
            scraper.all_items.extend(items)
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

        # Respect delay between auctions
        time.sleep(args.delay)

    # Save combined CSV
    out_path = scraper.save_to_csv(args.output)

    logger.info('Multi-auction full scrape complete')
    logger.info(f'Auctions scraped: {len(auctions)}')
    logger.info(f'Total items scraped: {total_items}')
    logger.info(f'Output CSV: {out_path if out_path else args.output}')
    logger.info(f'Run directory: {scraper.run_dir}')


if __name__ == '__main__':
    main()
