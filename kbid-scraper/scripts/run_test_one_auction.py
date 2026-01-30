"""Run a quick test scrape for a single auction.

This script uses the existing KBidScraper class and:
- discovers listing pages
- collects auction URLs
- selects the first unique auction
- streams results to results/test_kbid_auction_1.csv
- prints simple progress and exits

Usage:
    python run_test_one_auction.py

Adjust `delay` and `max_workers` below as needed for testing.
"""

import sys
import os

# Ensure the repository root (parent of scripts/) is on sys.path so imports like
# `from kbid_scraper import KBidScraper` work when this file is run directly.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from kbid_scraper import KBidScraper
import time
import os


def main():
    delay = 1.0
    output_file = 'test_kbid_auction_1.csv'

    scraper = KBidScraper(delay=delay)
    # Keep the test light but thorough enough
    scraper.max_workers = 2
    scraper.lazy = False  # fetch detailed fields for each item in test

    print(f"Starting quick single-auction test run (delay={delay}s, workers={scraper.max_workers})")

    if not scraper.start_streaming_csv(output_file):
        print("Could not open output file for streaming. Exiting.")
        return

    try:
        pages = scraper.get_auction_list_pages()
        if not pages:
            print("No listing pages found. Exiting.")
            return

        # collect auctions from pages
        all_auctions = []
        for p in pages:
            all_auctions.extend(scraper.get_auctions_from_page(p))

        # dedupe while preserving order
        all_auctions = list(dict.fromkeys(all_auctions))

        if not all_auctions:
            print("No auctions found after listing parsing. Exiting.")
            return

        # pick first auction for test
        test_auctions = all_auctions[:1]
        print(f"Found {len(all_auctions)} auctions, testing first {len(test_auctions)}: \n  " + "\n  ".join(test_auctions))

        for auction_url in test_auctions:
            print(f"\nProcessing test auction: {auction_url}")
            auction_info = scraper.extract_auction_details(auction_url)
            if not auction_info:
                print("  Failed to extract auction info, skipping")
                continue

            items = scraper.get_all_items_from_auction(auction_url, auction_info)
            print(f"  Items scraped for this auction: {len(items)}")
            # short delay so logs are readable
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("Interrupted by user (KeyboardInterrupt). Shutting down test run.")
    finally:
        scraper.stop_streaming_csv()
        scraper.save_summary()
        print("Test run complete. Outputs in results/ directory.")


if __name__ == '__main__':
    main()
