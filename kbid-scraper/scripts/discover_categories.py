"""
Discover K-Bid category IDs and counts from live category pages.

Usage:
  python .\scripts\discover_categories.py --output kbid_categories.csv
"""

import argparse
import csv
import os
import re
import sys
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import scraper_enhanced as se


TOP_LEVEL_CATEGORIES = [
    'Coins, Currency & Precious Metals',
    'Commercial & Industrial',
    'Farm Equipment',
    'Heavy Equipment & Construction',
    'Household & Estate',
    'Real Estate',
    'Sporting Goods & Hobbies',
    'Technology',
    'Vehicles & Marine',
]


def category_page_url(name):
    return f"https://www.k-bid.com/items/category/{quote_plus(name)}"


def extract_category_id(href):
    match = re.search(r'[?&]category_ids=(\d+)', href or '')
    return match.group(1) if match else None


def parse_count(text):
    match = re.search(r'\bView all\s+([\d,]+)\s+Lots?\b', text or '', re.I)
    return int(match.group(1).replace(',', '')) if match else None


def discover(scraper):
    rows = []
    seen = set()

    for top_level in TOP_LEVEL_CATEGORIES:
        url = category_page_url(top_level)
        response = scraper.get_with_retry(url)
        soup = BeautifulSoup(response.content, 'lxml')

        names_by_id = {}
        counts_by_id = {}
        urls_by_id = {}

        for link in soup.find_all('a', href=re.compile(r'[?&]category_ids=\d+')):
            category_id = extract_category_id(link.get('href'))
            if not category_id:
                continue

            text = link.get_text(' ', strip=True)
            urls_by_id[category_id] = urljoin(scraper.base_url, link['href'])
            count = parse_count(text)
            if count is not None:
                counts_by_id[category_id] = count
                continue
            if (
                text
                and not text.lower().startswith('view all')
                and text.lower() != 'no lots currently assigned here'
            ):
                names_by_id[category_id] = text

        for category_id, name in names_by_id.items():
            key = (top_level, category_id)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                'top_level_category': top_level,
                'subcategory': name,
                'category_id': category_id,
                'open_lot_count': counts_by_id.get(category_id, ''),
                'search_url': urls_by_id.get(category_id, ''),
            })

    return rows


def main():
    parser = argparse.ArgumentParser(description='Discover live K-Bid category_ids')
    parser.add_argument('--output', default='kbid_categories.csv', help='Output CSV path')
    parser.add_argument('--delay', type=float, default=0.5, help='Delay configured on scraper')
    args = parser.parse_args()

    scraper = se.KBidScraperFixed(delay=args.delay)
    rows = discover(scraper)

    output = args.output
    if not os.path.isabs(output):
        output = os.path.join(scraper.run_dir, output)

    with open(output, 'w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=['top_level_category', 'subcategory', 'category_id', 'open_lot_count', 'search_url']
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} categories to {output}")


if __name__ == '__main__':
    main()
