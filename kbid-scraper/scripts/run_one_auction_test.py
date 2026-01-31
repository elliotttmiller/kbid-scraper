"""
Run a quick test of scraper_enhanced.KBidScraperFixed

This script will:
- Find one auction (or use an explicit auction URL via --auction)
- Scrape up to --limit items (default 5)
- Save results to a CSV in the scraper's run directory

Usage (PowerShell):
  python .\kbid-scraper\scripts\run_one_auction_test.py --limit 5
  python .\kbid-scraper\scripts\run_one_auction_test.py --auction "https://www.k-bid.com/auction/12345" --limit 5

Note: This imports and uses the KBidScraperFixed class from scraper_enhanced.py.
"""

import argparse
import logging
import sys
import time
from urllib.parse import urljoin

# Ensure we can import scraper_enhanced from the repo folder
import os
import sys

# Make sure the parent folder (kbid-scraper) is on sys.path so we can import scraper_enhanced
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import scraper_enhanced as se

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description='Run a quick one-auction, N-item test for KBid scraper')
    parser.add_argument('--auction', '-a', help='Specific auction URL to test (optional)')
    parser.add_argument('--limit', '-n', type=int, default=5, help='Max number of items to collect (default: 5)')
    parser.add_argument('--delay', '-d', type=float, default=1.0, help='Delay between requests in seconds (default: 1.0)')
    parser.add_argument('--output', '-o', default='test_kbid_5_items.csv', help='Output CSV filename (saved in run dir)')

    args = parser.parse_args()

    logger.info('Starting quick test script')

    scraper = se.KBidScraperFixed(delay=args.delay)

    # Determine auction URL
    auction_url = args.auction
    if not auction_url:
        logger.info('No auction URL provided. Fetching listing pages to find the first auction...')
        try:
            list_pages = scraper.get_auction_list_pages()
            if not list_pages:
                logger.error('No listing pages found. Exiting.')
                sys.exit(1)

            # Use first listing page
            first_page = list_pages[0]
            auctions = scraper.get_auctions_from_page(first_page)
            if not auctions:
                logger.error('No auctions found on the first listing page. Exiting.')
                sys.exit(1)

            auction_url = auctions[0]
            logger.info(f'Using first discovered auction: {auction_url}')
        except Exception as e:
            logger.error(f'Error finding auction URL: {e}')
            sys.exit(1)

    # Scrape items for the selected auction (use max_items to avoid scraping all pages)
    try:
        items = scraper.scrape_auction_items(auction_url, max_items=args.limit)
    except Exception as e:
        logger.error(f'Error scraping auction items: {e}')
        items = []

    # Store scraped items
    scraper.all_items = items

    # Save results
    out_path = scraper.save_to_csv(args.output)

    logger.info('Quick test complete')
    logger.info(f'Output CSV: {out_path if out_path else args.output}')
    logger.info(f'Total items saved: {len(items)}')
    logger.info(f'Run directory: {scraper.run_dir}')


if __name__ == '__main__':
    main()
