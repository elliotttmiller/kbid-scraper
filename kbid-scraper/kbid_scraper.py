"""
K-Bid Auction Scraper
=====================
Comprehensive web scraper for k-bid.com auction listings

This scraper extracts:
- All live auction listings
- Complete item details from each auction
- Bids, categories, descriptions, images, and more
- Exports everything to CSV format

Author: Claude
Date: January 2026
"""

import requests
from bs4 import BeautifulSoup
import csv
import time
import re
from urllib.parse import urljoin, urlparse
from datetime import datetime
import logging
import sys
import threading
import json
from decimal import Decimal, InvalidOperation
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from collections import Counter
import os
import signal

# Ensure results directory exists and configure logging with UTF-8 encoding
RESULTS_DIR = 'results'
os.makedirs(RESULTS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(RESULTS_DIR, 'kbid_scraper.log'), encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# For Windows console compatibility
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'ignore')


class KBidScraper:
    """Main scraper class for K-Bid auctions"""
    
    def __init__(self, delay=1.0, include_fields=None):
        """
        Initialize the scraper
        
        Args:
            delay (float): Delay between requests in seconds (default: 1.0)
            include_fields (list): List of fields to include in the output (default: None, includes all fields)
        """
        self.base_url = "https://www.k-bid.com"
        self.delay = delay
        # Default to a full extraction schema (thorough run) unless user specifies a subset.
        full_fields = [
            'lot_number', 'item_title', 'short_description', 'current_bid', 'next_required_bid',
            'high_bidder', 'category', 'item_closing_time', 'item_url', 'image_url',
            'auction_id', 'auction_title', 'affiliate', 'location', 'phone', 'closing_date',
            'total_items', 'categories', 'auction_url'
        ]
        self.include_fields = include_fields if include_fields is not None else full_fields
        # By default run in thorough mode (fetch details for all items)
        self.lazy = False

        # Concurrency settings for detail fetches
        self.max_workers = 5

        # Only process auctions that are open (not closed/ended)
        # Set to True to skip auctions detected as closed
        self.only_open_auctions = True
        # When True, extract_auction_details will perform a page-level check for closed status
        # (slower but more accurate). If False, filtering will rely on listing-page signals only.
        self.check_auction_page_status = True

        # CSV streaming writer and lock (initialized when scrape starts)
        self.csv_file = None
        self.csv_writer = None
        self.csv_lock = threading.Lock()
        # Control flag to request graceful stop (e.g., on Ctrl+C)
        self.stop_requested = False

        # Track current executor so an external signal handler can shut it down
        self.current_executor = None

        # Deduplication set of seen item keys (item_url preferred)
        self.seen_item_keys = set()
        # Lock to protect seen_item_keys for thread-safe deduplication
        self.seen_lock = threading.Lock()

        # Per-field telemetry to track availability during runs
        self.field_stats = {
            'found': Counter(),
            'missing': Counter()
        }
        # Track where bid values were sourced from (listing_html, item_html, script_json, xhr_api, headless)
        self.bid_source_counter = Counter()
        # Debug failures sampling limit
        self._debug_failures_sampled = 0
        self._debug_failures_limit = 50
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
        })
        self.all_items = []
        self.stats = {
            'auctions_found': 0,
            'items_scraped': 0,
            'errors': 0,
            'start_time': None,
            'end_time': None
        }
    
    def get_auction_list_pages(self):
        """
        Get all auction listing page URLs
        
        Returns:
            list: List of auction listing page URLs
        """
        logger.info("Fetching auction list pages...")
        pages = []
        page_num = 1
        
        while True:
            url = f"{self.base_url}/auction/list?page={page_num}" if page_num > 1 else f"{self.base_url}/auction/list"
            
            try:
                response = self.session.get(url, timeout=15)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Check if there are auctions on this page
                auction_links = soup.find_all('a', href=re.compile(r'/auction/\d+$'))
                
                if not auction_links:
                    logger.info(f"No auctions found on page {page_num}, stopping pagination")
                    break
                    
                pages.append(url)
                logger.info(f"Found auction listing page {page_num}")
                
                # Check for next page button
                next_link = soup.find('a', string='Next »')
                if not next_link:
                    logger.info("No 'Next' button found, reached last page")
                    break
                    
                page_num += 1
                time.sleep(self.delay)
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching page {page_num}: {e}")
                self.stats['errors'] += 1
                break
            except Exception as e:
                logger.error(f"Unexpected error on page {page_num}: {e}")
                self.stats['errors'] += 1
                break
                
        logger.info(f"Total listing pages found: {len(pages)}")
        return pages
    
    def get_auctions_from_page(self, page_url):
        """
        Extract auction URLs from a listing page
        
        Args:
            page_url (str): URL of the listing page
            
        Returns:
            list: List of auction URLs
        """
        logger.info(f"Extracting auctions from: {page_url}")
        auctions = []
        
        try:
            response = self.session.get(page_url, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find all auction links (they follow pattern /auction/NUMBER)
            auction_links = soup.find_all('a', href=re.compile(r'/auction/\d+$'))
            
            seen = set()
            for link in auction_links:
                href = link.get('href')
                if href and href not in seen:
                    full_url = urljoin(self.base_url, href)
                    seen.add(href)
                    auctions.append(full_url)
                    
            logger.info(f"Found {len(auctions)} unique auctions on this page")
            time.sleep(self.delay)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error extracting auctions: {e}")
            self.stats['errors'] += 1
        except Exception as e:
            logger.error(f"Error extracting auctions: {e}")
            self.stats['errors'] += 1
            
        return auctions
    
    def extract_auction_details(self, auction_url):
        """
        Extract basic auction information from auction page
        
        Args:
            auction_url (str): URL of the auction
            
        Returns:
            dict: Auction details or None if error
        """
        try:
            response = self.session.get(auction_url, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract auction title
            title = soup.find('h1')
            title_text = title.get_text(strip=True) if title else "N/A"
            
            # Extract affiliate/auctioneer name
            affiliate_section = soup.find('h4', class_=False)
            affiliate_name = "N/A"
            if affiliate_section:
                # Check if it's not a "Lot:" heading
                text = affiliate_section.get_text(strip=True)
                if 'Lot:' not in text and 'Begins Closing' not in text:
                    affiliate_name = text
            
            # Extract location
            location = "N/A"
            location_label = soup.find(string=re.compile(r'Auction Location:', re.I))
            if location_label:
                location_parent = location_label.find_parent()
                if location_parent:
                    location_text = location_parent.get_text(strip=True)
                    location = location_text.replace('Auction Location:', '').strip()
            
            # Extract phone
            phone = "N/A"
            phone_link = soup.find('a', href=re.compile(r'^tel:'))
            if phone_link:
                phone = phone_link.get_text(strip=True)
            
            # Extract closing date/time
            closing_date = "N/A"
            closing_elem = soup.find(string=re.compile(r'Begins Closing', re.I))
            if closing_elem:
                closing_parent = closing_elem.find_parent()
                if closing_parent:
                    # Try to get the next sibling or nearby date element
                    date_elem = closing_parent.find_next(['strong', 'b', 'span'])
                    if date_elem:
                        closing_date = date_elem.get_text(strip=True)
            
            # Extract total item count
            item_count = 0
            # Look for "X Items" text
            items_text = soup.find(string=re.compile(r'\d+\s+Items', re.I))
            if items_text:
                match = re.search(r'(\d+)\s+Items', items_text, re.I)
                if match:
                    item_count = int(match.group(1))
            
            # Extract lot categories (if available)
            categories = []
            category_links = soup.find_all('a', href=re.compile(r'category_ids='))
            for cat_link in category_links[:10]:  # Limit to first 10
                cat_text = cat_link.get_text(strip=True)
                if cat_text and cat_text not in categories:
                    categories.append(cat_text)
            
            return {
                'auction_url': auction_url,
                'auction_id': auction_url.split('/')[-1],
                'auction_title': title_text,
                'affiliate': affiliate_name,
                'location': location,
                'phone': phone,
                'closing_date': closing_date,
                'total_items': item_count,
                'categories': '; '.join(categories) if categories else "N/A"
            }

            # Determine auction status (open/closed) conservatively
            # We'll attempt a page-level check for explicit closed/ended markers when configured.
            status = 'unknown'
            try:
                # If configured to check page-level markers, look for obvious closed/ended phrases
                if hasattr(self, 'check_auction_page_status') and self.check_auction_page_status:
                    closed_marker = soup.find(string=re.compile(r'(?:(auction has|has) ended|ended|closed|no longer accepting bids|sold)', re.I))
                    if closed_marker:
                        status = 'closed'
                    else:
                        # If page contains 'Begins Closing' or similar, treat as open
                        begins = soup.find(string=re.compile(r'Begins Closing|Begins|Starts Closing|Time Remaining', re.I))
                        if begins:
                            status = 'open'
                else:
                    # Infer status from closing_date string when page-level check disabled
                    if closing_date and re.search(r'ended|closed', closing_date, re.I):
                        status = 'closed'
                    elif closing_date and re.search(r'Begins Closing|Today|Starts', closing_date, re.I):
                        status = 'open'
            except Exception:
                status = 'unknown'

            # Attach status into returned metadata
            result = {
                'auction_url': auction_url,
                'auction_id': auction_url.split('/')[-1],
                'auction_title': title_text,
                'affiliate': affiliate_name,
                'location': location,
                'phone': phone,
                'closing_date': closing_date,
                'total_items': item_count,
                'categories': '; '.join(categories) if categories else "N/A",
                'status': status
            }

            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error extracting auction details from {auction_url}: {e}")
            self.stats['errors'] += 1
            return None
        except Exception as e:
            logger.error(f"Error extracting auction details from {auction_url}: {e}")
            self.stats['errors'] += 1
            return None
    
    def get_all_items_from_auction(self, auction_url, auction_info):
        """
        Get all items from a specific auction (handles pagination)
        
        Args:
            auction_url (str): URL of the auction
            auction_info (dict): Auction metadata
            
        Returns:
            list: List of item dictionaries
        """
        logger.info(f"Scraping items from: {auction_info['auction_title'][:60]}...")
        items = []
        page_num = 1
        
        # Decide whether we need to fetch detailed fields from item pages.
        detail_fields = set([
            'short_description', 'current_bid', 'next_required_bid', 'high_bidder',
            'category', 'image_url', 'item_closing_time'
        ])
        need_detail = not self.lazy and any(f in self.include_fields for f in detail_fields)

        while True:
            if self.stop_requested:
                logger.info("Stop requested, aborting item pagination for this auction")
                break
            page_url = f"{auction_url}?page={page_num}" if page_num > 1 else auction_url
            
            try:
                response = self.session.get(page_url, timeout=15)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Multiple strategies to find items
                lot_headings = []
                
                # Strategy 1: Look for "Lot: NUMBER" in various heading tags
                for tag in ['h4', 'h5', 'h3', 'h6']:
                    found = soup.find_all(tag, string=re.compile(r'Lot:\s*\d+', re.I))
                    lot_headings.extend(found)
                
                # Strategy 2: Look for lot links pattern
                if not lot_headings:
                    lot_links = soup.find_all('a', href=re.compile(r'/auction/\d+/item/\d+'))
                    # Get parent containers that have item info
                    seen_containers = set()
                    for link in lot_links:
                        parent = link.find_parent(['div', 'article', 'section'])
                        if parent and id(parent) not in seen_containers:
                            seen_containers.add(id(parent))
                            lot_headings.append(link)
                
                # Strategy 3: Look for divs/sections with item content
                if not lot_headings:
                    # Find containers that have both an image and bid information
                    containers = soup.find_all(['div', 'article', 'section'])
                    for container in containers:
                        if (container.find(string=re.compile(r'Current Bid|Lot:', re.I)) and 
                            (container.find('img') or container.find('a', href=re.compile(r'/item/')))):
                            lot_headings.append(container)
                
                if not lot_headings:
                    logger.info(f"  No more items found on page {page_num}")
                    break
                
                logger.info(f"  Page {page_num}: Processing {len(lot_headings)} items...")

                # First pass: extract lightweight fields from container (no item page fetch)
                base_items = []
                for lot_elem in lot_headings:
                    try:
                        base_item = self.extract_item_details(lot_elem, auction_info, fetch_details=False)
                        if base_item:
                                base_items.append(base_item)
                    except Exception as e:
                        logger.warning(f"    Error extracting base item: {e}")
                        self.stats['errors'] += 1
                        continue

                # If detailed fields are required, fetch item pages concurrently and stream rows
                if need_detail and base_items:
                    with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                        # expose the executor so signal handler can shut it down
                        self.current_executor = executor
                        futures = [executor.submit(self.fetch_item_page_details, it) for it in base_items]
                        try:
                            for future in as_completed(futures):
                                if self.stop_requested:
                                    logger.info("Stop requested, cancelling remaining detail fetches")
                                    break
                                try:
                                    item = future.result()
                                except Exception as e:
                                    logger.warning(f"    Error fetching item page details: {e}")
                                    self.stats['errors'] += 1
                                    continue

                                # Update telemetry
                                for field in self.include_fields:
                                    val = item.get(field, None)
                                    if val is None or val == '' or val == 'N/A':
                                        self.field_stats['missing'][field] += 1
                                    else:
                                        self.field_stats['found'][field] += 1

                                # Deduplicate by item key (thread-safe)
                                key = self.make_item_key(item)
                                with self.seen_lock:
                                    if key in self.seen_item_keys:
                                        logger.debug(f"Skipping duplicate item: {key}")
                                        continue
                                    self.seen_item_keys.add(key)

                                # Stream write to CSV if writer is available
                                if self.csv_writer:
                                    try:
                                        with self.csv_lock:
                                            self.csv_writer.writerow({k: item.get(k, '') for k in self.csv_writer.fieldnames})
                                    except Exception as e:
                                        logger.warning(f"    Could not write item to CSV: {e}")

                                items.append(item)
                        finally:
                            # clear executor reference
                            self.current_executor = None
                else:
                    # No detail fetch required: stream base_items
                    for item in base_items:
                        if self.stop_requested:
                            logger.info("Stop requested, aborting base item processing")
                            break

                        for field in self.include_fields:
                            val = item.get(field, None)
                            if val is None or val == '' or val == 'N/A':
                                self.field_stats['missing'][field] += 1
                            else:
                                self.field_stats['found'][field] += 1

                        key = self.make_item_key(item)
                        with self.seen_lock:
                            if key in self.seen_item_keys:
                                logger.debug(f"Skipping duplicate item: {key}")
                                continue
                            self.seen_item_keys.add(key)

                        if self.csv_writer:
                            try:
                                with self.csv_lock:
                                    self.csv_writer.writerow({k: item.get(k, '') for k in self.csv_writer.fieldnames})
                            except Exception as e:
                                logger.warning(f"    Could not write item to CSV: {e}")

                        items.append(item)
                
                # Check for next page
                next_link = soup.find('a', string=re.compile(r'Next\s*»', re.I))
                if not next_link:
                    logger.info(f"  No more pages for this auction")
                    break
                    
                page_num += 1
                time.sleep(self.delay)
                
            except requests.exceptions.RequestException as e:
                logger.error(f"  Request error on page {page_num}: {e}")
                self.stats['errors'] += 1
                break
            except Exception as e:
                logger.error(f"  Error on page {page_num}: {e}")
                self.stats['errors'] += 1
                break
        
        logger.info(f"  Total items scraped from this auction: {len(items)}")
        return items
    
    def extract_item_details(self, lot_elem, auction_info, fetch_details=True):
        """
        Extract detailed information about a specific item
        
        Args:
            lot_elem: BeautifulSoup element containing lot information
            auction_info (dict): Parent auction information
            
        Returns:
            dict: Item details
        """
        item = auction_info.copy()
        
        # Determine if lot_elem is the container itself or needs parent
        if lot_elem.name == 'a' or lot_elem.name in ['h4', 'h5', 'h3', 'h6']:
            # Need to find parent container
            container = lot_elem.find_parent(['div', 'article', 'section'])
            if not container:
                # Try broader search
                container = lot_elem.parent
        else:
            # Element is already the container
            container = lot_elem
        
        if not container:
            return None
        
        # Get lot number - try multiple methods
        lot_number = "N/A"
        
        # Method 1: Look for "Lot: NUMBER" text
        lot_text = container.get_text()
        lot_match = re.search(r'Lot:\s*(\d+\w*)', lot_text, re.I)
        if lot_match:
            lot_number = lot_match.group(1)
        
        # Method 2: Extract from URL
        if lot_number == "N/A":
            lot_link = container.find('a', href=re.compile(r'/item/(\d+)'))
            if lot_link:
                url_match = re.search(r'/item/(\d+)', lot_link['href'])
                if url_match:
                    lot_number = url_match.group(1)
        
        item['lot_number'] = lot_number
        
        # Get item title/description. If we are not fetching details, prefer lightweight title discovery.
        item['item_title'] = "N/A"
        title_elem = None
        if hasattr(container, 'find'):
            # Prefer heading text first
            title_elem = container.find(['h2', 'h3', 'h4', 'h5'])
            if not title_elem:
                # Look for a link to the item and use its text if obvious
                link_candidate = container.find('a', href=re.compile(r'/item/'))
                if link_candidate and link_candidate.get_text(strip=True) and 'Click for Details' not in link_candidate.get_text(strip=True):
                    title_elem = link_candidate

        if title_elem:
            item['item_title'] = title_elem.get_text(strip=True)
        
        # Get item URL (always try to get URL so we can do lazy detail fetches later)
        item['item_url'] = "N/A"
        item_link = container.find('a', href=re.compile(r'/item/')) if hasattr(container, 'find') else None
        if item_link and item_link.get('href'):
            item['item_url'] = urljoin(self.base_url, item_link['href'])
        
        # Get current bid (only if fetching details)
        if fetch_details:
            bid_elem = container.find(string=re.compile(r'Current Bid', re.I)) if hasattr(container, 'find') else None
            if bid_elem:
                bid_parent = bid_elem.find_parent()
                if bid_parent:
                    bid_text = bid_parent.find_next().get_text(strip=True) if bid_parent.find_next() else bid_parent.get_text(strip=True)
                    bid_match = re.search(r'\$?([\d,]+\.?\d*)', bid_text)
                    item['current_bid'] = bid_match.group(1).replace(',', '') if bid_match else "0.00"
                else:
                    item['current_bid'] = "0.00"
            else:
                item['current_bid'] = "0.00"
        else:
            item['current_bid'] = "N/A"
        
        # Get next required bid (only if fetching details)
        if fetch_details:
            next_bid_elem = container.find(string=re.compile(r'Next Required Bid', re.I)) if hasattr(container, 'find') else None
            if next_bid_elem:
                next_parent = next_bid_elem.find_parent()
                if next_parent:
                    next_text = next_parent.find_next().get_text(strip=True) if next_parent.find_next() else next_parent.get_text(strip=True)
                    next_match = re.search(r'\$?([\d,]+\.?\d*)', next_text)
                    item['next_required_bid'] = next_match.group(1).replace(',', '') if next_match else "N/A"
                else:
                    item['next_required_bid'] = "N/A"
            else:
                item['next_required_bid'] = "N/A"
        else:
            item['next_required_bid'] = "N/A"
        
        # Get high bidder (only if fetching details)
        if fetch_details:
            bidder_elem = container.find(string=re.compile(r'High Bidder', re.I)) if hasattr(container, 'find') else None
            if bidder_elem:
                bidder_parent = bidder_elem.find_parent()
                if bidder_parent:
                    bidder_text = bidder_parent.get_text(strip=True).replace('High Bidder:', '').replace('High Bidder', '').strip()
                    item['high_bidder'] = bidder_text if bidder_text else "No bids"
                else:
                    item['high_bidder'] = "No bids"
            else:
                item['high_bidder'] = "No bids"
        else:
            item['high_bidder'] = "N/A"
        
        # Get category (only if fetching details)
        if fetch_details:
            category_elem = container.find('a', href=re.compile(r'category_ids=')) if hasattr(container, 'find') else None
            item['category'] = category_elem.get_text(strip=True) if category_elem else "N/A"
        else:
            item['category'] = "N/A"
        
        # Get image URL (only if fetching details)
        if fetch_details:
            img_elem = container.find('img', src=True) if hasattr(container, 'find') else None
            if img_elem and img_elem.get('src'):
                # Handle both absolute and relative URLs
                img_url = img_elem['src']
                if not img_url.startswith('http'):
                    img_url = urljoin(self.base_url, img_url)
                item['image_url'] = img_url
            else:
                item['image_url'] = "N/A"
        else:
            item['image_url'] = "N/A"
        
        # Get item closing time (only if fetching details)
        if fetch_details:
            time_elem = container.find(string=re.compile(r'Begins Closing|Time Remaining', re.I)) if hasattr(container, 'find') else None
            if time_elem:
                time_parent = time_elem.find_parent()
                if time_parent:
                    time_text = time_parent.get_text(strip=True)
                    # Clean up the text
                    time_text = re.sub(r'(Begins Closing:|Time Remaining:)', '', time_text, flags=re.I).strip()
                    item['item_closing_time'] = time_text
                else:
                    item['item_closing_time'] = "N/A"
            else:
                item['item_closing_time'] = "N/A"
        else:
            item['item_closing_time'] = "N/A"
        
        # Get item description (if fetching details)
        if fetch_details:
            desc_elem = container.find('p', class_=lambda x: x and 'desc' in x.lower() if x else False) if hasattr(container, 'find') else None
            item['short_description'] = desc_elem.get_text(strip=True)[:500] if desc_elem else "N/A"
        else:
            item['short_description'] = "N/A"
        
        return item

    def fetch_item_page_details(self, item):
        """Fetch the item page and populate detailed fields when available.

        This method is safe to run in worker threads. It respects self.delay between requests
        (simple per-worker sleep) to provide basic rate-limiting.
        """
        if self.stop_requested:
            return item

        item_url = item.get('item_url')
        if not item_url or item_url == 'N/A':
            return item

        # Respect a small delay per request to avoid hammering the server
        try:
            time.sleep(self.delay)
            resp = self.session.get(item_url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, 'html.parser')

            # Try to extract a more reliable title if present
            title_h = soup.find(['h1', 'h2', 'h3'])
            if title_h and title_h.get_text(strip=True):
                item['item_title'] = title_h.get_text(strip=True)

            # Current bid
            bid_elem = soup.find(string=re.compile(r'Current Bid', re.I))
            if bid_elem:
                bid_parent = bid_elem.find_parent()
                if bid_parent:
                    next_text = bid_parent.find_next().get_text(strip=True) if bid_parent.find_next() else bid_parent.get_text(strip=True)
                    m = re.search(r'\$?([\d,]+\.?\d*)', next_text)
                    if m:
                        item['current_bid'] = m.group(1).replace(',', '')

            # High bidder
            bidder_elem = soup.find(string=re.compile(r'High Bidder', re.I))
            if bidder_elem:
                bp = bidder_elem.find_parent()
                if bp:
                    txt = bp.get_text(strip=True).replace('High Bidder:', '').strip()
                    item['high_bidder'] = txt if txt else item.get('high_bidder', 'No bids')

            # Image: try og:image meta or main image
            meta_img = soup.find('meta', property='og:image')
            if meta_img and meta_img.get('content'):
                item['image_url'] = meta_img['content']
            else:
                img = soup.find('img', src=True)
                if img and img.get('src'):
                    item['image_url'] = urljoin(self.base_url, img['src'])

            # Short description: meta description or page paragraph
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc and meta_desc.get('content'):
                item['short_description'] = meta_desc.get('content')[:500]
            else:
                p = soup.find('p')
                if p and p.get_text(strip=True):
                    item['short_description'] = p.get_text(strip=True)[:500]

            # Category: look for category links
            cat = soup.find('a', href=re.compile(r'category_ids='))
            if cat:
                item['category'] = cat.get_text(strip=True)

            # Item closing time
            time_elem = soup.find(string=re.compile(r'Begins Closing|Time Remaining', re.I))
            if time_elem:
                tp = time_elem.find_parent()
                if tp:
                    ttext = tp.get_text(strip=True)
                    ttext = re.sub(r'(Begins Closing:|Time Remaining:)', '', ttext, flags=re.I).strip()
                    item['item_closing_time'] = ttext
            # ------------------ Enhanced bid extraction fallbacks ------------------
            # If current_bid is missing or suspicious (0.00), try a series of fallbacks:
            cur = item.get('current_bid')
            parsed_cur = self.parse_money(cur) if cur and cur not in ('N/A', '') else None

            if not parsed_cur or parsed_cur == '0.00':
                # 1) Try label/value search on the item page HTML
                lbl = self.find_label_value(soup, label_regexes=[re.compile(r'Current\s*Bid', re.I), re.compile(r'Bid', re.I)])
                parsed = self.parse_money(lbl) if lbl else None
                if parsed:
                    item['current_bid'] = parsed
                    self.bid_source_counter['item_html'] += 1
                    parsed_cur = parsed

            if not parsed_cur or parsed_cur == '0.00':
                # 2) Scan scripts for JSON blobs containing bid information
                for obj in self.scan_scripts_for_json(soup):
                    # recursively search for numeric price-like fields but avoid keys like 'highBidder' (IDs)
                    def _is_price_key(k):
                        if not k:
                            return False
                        kl = str(k).lower()
                        # require that key mentions bid/price AND also a qualifier indicating amount/current/value
                        if ('price' in kl) or ('amount' in kl) or ('current' in kl) or ('value' in kl) or ('next' in kl):
                            return True
                        # also accept explicit names
                        if kl in ('currentbid', 'current_bid', 'bidamount', 'current_price'):
                            return True
                        return False

                    def _search_json_for_price(o):
                        if isinstance(o, dict):
                            for k, v in o.items():
                                try:
                                    if _is_price_key(k):
                                        # candidate value
                                        if isinstance(v, (int, float)):
                                            return format(Decimal(v).quantize(Decimal('0.01')), 'f')
                                        if isinstance(v, str):
                                            p = self.parse_money(v)
                                            if p:
                                                return p
                                    # otherwise recurse
                                    res = _search_json_for_price(v)
                                    if res:
                                        return res
                                except Exception:
                                    continue
                        elif isinstance(o, list):
                            for it in o:
                                res = _search_json_for_price(it)
                                if res:
                                    return res
                        return None

                    try:
                        p = _search_json_for_price(obj)
                        if p:
                            item['current_bid'] = p
                            self.bid_source_counter['script_json'] += 1
                            parsed_cur = p
                            break
                    except Exception:
                        continue

            if not parsed_cur or parsed_cur == '0.00':
                # 3) Probe candidate API/XHR endpoints discovered on the page
                endpoints = self.find_candidate_api_urls(soup)
                for ep in endpoints:
                    try:
                        # conservative probe
                        r = self.session.get(ep, timeout=8)
                        if r.status_code == 200:
                            try:
                                j = r.json()
                                # reuse same recursive search
                                def _search_json_resp(jobj):
                                    def _is_price_key_local(k):
                                        if not k:
                                            return False
                                        kl = str(k).lower()
                                        if ('price' in kl) or ('amount' in kl) or ('current' in kl) or ('value' in kl) or ('next' in kl):
                                            return True
                                        if kl in ('currentbid', 'current_bid', 'bidamount', 'current_price'):
                                            return True
                                        return False

                                    if isinstance(jobj, dict):
                                        for kk, vv in jobj.items():
                                            try:
                                                if _is_price_key_local(kk):
                                                    if isinstance(vv, (int, float)):
                                                        return format(Decimal(vv).quantize(Decimal('0.01')), 'f')
                                                    if isinstance(vv, str):
                                                        p = self.parse_money(vv)
                                                        if p:
                                                            return p
                                                res = _search_json_resp(vv)
                                                if res:
                                                    return res
                                            except Exception:
                                                continue
                                    elif isinstance(jobj, list):
                                        for it in jobj:
                                            res = _search_json_resp(it)
                                            if res:
                                                return res
                                    return None

                                p = _search_json_resp(j)
                                if p:
                                    item['current_bid'] = p
                                    self.bid_source_counter['xhr_api'] += 1
                                    parsed_cur = p
                                    break
                            except ValueError:
                                # not JSON, skip
                                pass
                    except Exception:
                        continue

            # If still missing/zero and we haven't sampled too many failures, record a debug row
            if (not parsed_cur or parsed_cur == '0.00') and self._debug_failures_sampled < self._debug_failures_limit:
                try:
                    dbg_path = os.path.join(RESULTS_DIR, 'debug_bid_failures.csv')
                    header = ['auction_id', 'lot_number', 'item_url', 'found_current_bid', 'sample_script_snippet']
                    write_header = not os.path.exists(dbg_path)
                    snippet = ''
                    # take first script tag text up to 200 chars for debugging
                    s = soup.find('script')
                    if s:
                        snippet = (s.string or s.text or '')[:200]
                    with self.csv_lock:
                        with open(dbg_path, 'a', encoding='utf-8', newline='') as df:
                            writer = csv.writer(df)
                            if write_header:
                                writer.writerow(header)
                            writer.writerow([item.get('auction_id'), item.get('lot_number'), item_url, item.get('current_bid'), snippet])
                    self._debug_failures_sampled += 1
                except Exception:
                    pass
        except Exception as e:
            # Keep best-effort; don't fail the whole run for individual item errors
            logger.debug(f"fetch_item_page_details error for {item_url}: {e}")
            self.stats['errors'] += 1

        return item

    def make_item_key(self, item):
        """Return a stable unique key for an item to detect duplicates."""
        url = item.get('item_url')
        # Prefer a canonicalized URL (strip query params/fragments)
        if url and url != 'N/A':
            try:
                parsed = urlparse(url)
                # Keep only scheme+netloc+path to avoid query-string variation (e.g., ?offset=)
                path = parsed.path.rstrip('/')
                if not path:
                    return url
                return f"{parsed.scheme}://{parsed.netloc}{path}"
            except Exception:
                return url

        # Fallback to auction_id + normalized lot_number + title snippet
        aid = str(item.get('auction_id', '')).strip()
        lot = str(item.get('lot_number', '')).strip()
        # Normalize lot to digits where possible
        lot_match = re.search(r"(\d+)", lot)
        lot_norm = lot_match.group(1) if lot_match else lot
        title = str(item.get('item_title', '')).strip().lower()
        # compact whitespace in title
        title_norm = re.sub(r"\s+", " ", title)[:80]
        return f"{aid}:{lot_norm}:{title_norm}"

    # ----------------------- Parsing helper utilities -----------------------
    def parse_money(self, text):
        """Parse a money string into a normalized string with two decimals (e.g., '14.00').

        Returns None if parsing fails.
        """
        if not text:
            return None
        try:
            # remove common currency symbols and whitespace
            t = re.sub(r'[,$£€\s]', '', str(text))
            # keep digits and dot
            m = re.search(r'(-?\d+[\d,]*\.?\d*)', t)
            if not m:
                return None
            num = m.group(1).replace(',', '')
            d = Decimal(num)
            # Format with two decimal places
            return format(d.quantize(Decimal('0.01')), 'f')
        except (InvalidOperation, Exception):
            return None

    def find_label_value(self, container, label_regexes=None):
        """Search a container for textual label(s) and return the nearest money-like value.

        label_regexes: list of compiled regex or strings to match labels like 'Current Bid'.
        Returns the raw matched string or None.
        """
        if container is None:
            return None
        if label_regexes is None:
            label_regexes = [re.compile(r'Current\s*Bid', re.I)]
        money_re = re.compile(r'[$£€]?\s*([\d,]+\.?\d{0,2})')
        money_with_sym_re = re.compile(r'[$£€]\s*[\d,]+\.?\d{0,2}')

        # Search for label text nodes first
        for lr in label_regexes:
            nodes = container.find_all(string=lr) if hasattr(container, 'find_all') else []
            for node in nodes:
                try:
                    parent = node.find_parent()
                    # check sibling or nearby text nodes
                    # 1) next sibling string
                    if parent:
                        # Prefer a nearby token that includes a currency symbol
                        nxt_sym = parent.find_next(string=money_with_sym_re)
                        if nxt_sym:
                            m = money_with_sym_re.search(nxt_sym)
                            if m:
                                return m.group(0)
                        # Fallback: first numeric token in proximity
                        nxt = parent.find_next(string=money_re)
                        if nxt:
                            m = money_re.search(nxt)
                            if m:
                                return m.group(0)
                        # 2) check parent text for a money token
                        m2 = money_re.search(parent.get_text(' ', strip=True))
                        if m2:
                            return m2.group(0)
                    # 3) fallback: search container text after label occurrence
                    full = container.get_text(' ', strip=True)
                    idx = full.lower().find(str(node).lower())
                    if idx != -1:
                        tail = full[idx:idx+200]
                        m3 = money_re.search(tail)
                        if m3:
                            return m3.group(0)
                except Exception:
                    continue

        # Global fallback: search for any money-looking token in container
        try:
            all_text = container.get_text(' ', strip=True)
            # Prefer tokens that include currency symbol
            m_sym = money_with_sym_re.search(all_text)
            if m_sym:
                return m_sym.group(0)
            m = money_re.search(all_text)
            if m:
                return m.group(0)
        except Exception:
            pass

        return None

    def scan_scripts_for_json(self, soup, keywords=None):
        """Scan script tags for JSON blobs (ld+json or JS objects) containing any of the keywords.

        Yields parsed JSON objects (dict) when found.
        """
        if keywords is None:
            keywords = ['currentBid', 'current_bid', 'bidAmount', 'current_price', 'price']

        scripts = soup.find_all('script')
        for script in scripts:
            try:
                stype = script.get('type', '').lower()
                text = script.string or ''
                if not text:
                    # sometimes script contents are in .text
                    text = script.text or ''

                # If ld+json try direct parse
                if 'ld+json' in stype:
                    try:
                        obj = json.loads(text)
                        # quick check for keywords
                        jtext = json.dumps(obj).lower()
                        if any(k.lower() in jtext for k in keywords):
                            yield obj
                    except Exception:
                        # ignore malformed ld+json
                        pass

                # Keyword present in script body? attempt to extract JSON-like object
                low = text.lower()
                if any(k.lower() in low for k in keywords):
                    # Try to extract the first JSON-like substring containing the keyword
                    for k in keywords:
                        ki = low.find(k.lower())
                        if ki == -1:
                            continue
                        # search backwards for nearest '{'
                        start = text.rfind('{', 0, ki)
                        end = text.find('}', ki)
                        if start != -1 and end != -1 and end > start:
                            cand = text[start:end+1]
                            # attempt to sanitize common JS to JSON issues
                            cand_fixed = re.sub(r',\s*}', '}', cand)
                            cand_fixed = re.sub(r',\s*]', ']', cand_fixed)
                            try:
                                obj = json.loads(cand_fixed)
                                yield obj
                                break
                            except Exception:
                                # If naive extraction failed, try a looser regex for brace-balanced block
                                # As a last resort skip
                                continue

            except Exception:
                continue

    def find_candidate_api_urls(self, soup):
        """Scan scripts and page text for candidate API endpoints (strings with '/api' or '.json').

        Returns a list of absolute URLs (may be relative) discovered on the page.
        """
        candidates = set()
        # Search script bodies for /api/ or .json occurrences
        scripts = soup.find_all('script')
        for script in scripts:
            txt = script.string or script.text or ''
            for m in re.finditer(r"['\"](/[^'\"]+?(?:api|xhr|json)[^'\"]*)['\"]", txt, re.I):
                candidates.add(m.group(1))

        # Also scan for obvious endpoints in anchor hrefs
        for a in soup.find_all('a', href=True):
            href = a['href']
            if '.json' in href or '/api/' in href or '/xhr/' in href:
                candidates.add(href)

        # Convert to absolute using base_url
        abs_urls = [urljoin(self.base_url, u) for u in candidates]
        return list(abs_urls)
    
    def scrape_all_auctions(self):
        """
        Main method to scrape all auctions and items
        
        Returns:
            list: List of all scraped items
        """
        self.stats['start_time'] = datetime.now()
        
        logger.info("=" * 80)
        logger.info("K-BID AUCTION SCRAPER - STARTED")
        logger.info("=" * 80)
        logger.info(f"Start time: {self.stats['start_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Delay between requests: {self.delay}s")
        logger.info("")
        
        # Step 1: Get all listing pages
        list_pages = self.get_auction_list_pages()
        
        if not list_pages:
            logger.error("No listing pages found! Exiting.")
            return []
        
        logger.info("")
        
        # Step 2: Get all auction URLs from listing pages
        all_auctions = []
        for page_url in list_pages:
            auctions = self.get_auctions_from_page(page_url)
            all_auctions.extend(auctions)
        
        # Remove duplicates
        all_auctions = list(set(all_auctions))
        self.stats['auctions_found'] = len(all_auctions)
        
        logger.info("")
        logger.info("=" * 80)
        logger.info(f"FOUND {len(all_auctions)} UNIQUE AUCTIONS")
        logger.info("=" * 80)
        logger.info("")
        
        # Step 3: Scrape each auction
        for idx, auction_url in enumerate(all_auctions, 1):
            logger.info(f"[{idx}/{len(all_auctions)}] Processing auction...")
            logger.info(f"  URL: {auction_url}")
            
            # Get auction details
            auction_info = self.extract_auction_details(auction_url)
            if not auction_info:
                logger.warning("  ⚠ Could not extract auction details, skipping...")
                continue

            # If configured, skip auctions that are detected as closed
            if getattr(self, 'only_open_auctions', False):
                status = auction_info.get('status', 'unknown')
                if status == 'closed':
                    logger.info(f"  Skipping auction (status=closed): {auction_info.get('auction_title','')}")
                    continue
            
            logger.info(f"  Title: {auction_info['auction_title'][:70]}...")
            logger.info(f"  Affiliate: {auction_info['affiliate']}")
            logger.info(f"  Items: {auction_info['total_items']}")
            
            # Get all items from this auction
            items = self.get_all_items_from_auction(auction_url, auction_info)
            self.all_items.extend(items)
            self.stats['items_scraped'] += len(items)
            
            logger.info("")
            time.sleep(self.delay)
        
        self.stats['end_time'] = datetime.now()
        duration = self.stats['end_time'] - self.stats['start_time']
        
        logger.info("")
        logger.info("=" * 80)
        logger.info("SCRAPING COMPLETE!")
        logger.info("=" * 80)
        logger.info(f"Auctions processed: {self.stats['auctions_found']}")
        logger.info(f"Total items scraped: {self.stats['items_scraped']}")
        logger.info(f"Errors encountered: {self.stats['errors']}")
        logger.info(f"Duration: {duration}")
        logger.info(f"End time: {self.stats['end_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 80)
        logger.info("")

        # After run, report field availability telemetry (if any)
        try:
            self.report_field_stats()
        except Exception:
            pass

        return self.all_items

    def report_field_stats(self):
        """Log a compact report of per-field availability observed during the run."""
        total_seen = self.stats.get('items_scraped', 0) or len(self.all_items)
        if not (self.field_stats['found'] or self.field_stats['missing']):
            logger.info("No per-field telemetry collected.")
            return

        logger.info("Field availability summary:")
        for field in self.include_fields:
            found = self.field_stats['found'].get(field, 0)
            missing = self.field_stats['missing'].get(field, 0)
            pct_missing = (missing / max(found + missing, 1)) * 100
            logger.info(f"  {field:20} found: {found:6d}  missing: {missing:6d}  %missing: {pct_missing:5.1f}%")

        # Also write a small summary file in the results directory
        try:
            out_path = os.path.join(RESULTS_DIR, 'field_availability_summary.txt')
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write('Field availability summary\n')
                f.write('=' * 60 + '\n')
                for field in self.include_fields:
                    found = self.field_stats['found'].get(field, 0)
                    missing = self.field_stats['missing'].get(field, 0)
                    pct_missing = (missing / max(found + missing, 1)) * 100
                    f.write(f"{field:20} found: {found:6d}  missing: {missing:6d}  %missing: {pct_missing:5.1f}%\n")
            logger.info(f"Wrote field availability summary to {out_path}")
        except Exception:
            logger.warning("Could not write field availability summary file.")

    def start_streaming_csv(self, filename='kbid_auctions_data.csv'):
        """Open a CSV file and prepare a streaming writer. Thread-safe via self.csv_lock."""
        try:
            # Normalize path into results directory unless an absolute path was provided
            if not os.path.isabs(filename):
                filename = os.path.join(RESULTS_DIR, filename)
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            self.csv_file = open(filename, 'w', newline='', encoding='utf-8')
            # Ensure header order follows include_fields
            headers = [h for h in [
                'lot_number', 'item_title', 'short_description', 'current_bid', 'next_required_bid',
                'high_bidder', 'category', 'item_closing_time', 'item_url', 'image_url',
                'auction_id', 'auction_title', 'affiliate', 'location', 'phone', 'closing_date',
                'total_items', 'categories', 'auction_url'
            ] if h in self.include_fields]
            self.csv_writer = csv.DictWriter(self.csv_file, fieldnames=headers, extrasaction='ignore')
            self.csv_writer.writeheader()
            logger.info(f"Streaming CSV output initialized: {filename}")
            return True
        except Exception as e:
            logger.error(f"Could not initialize streaming CSV: {e}")
            self.csv_file = None
            self.csv_writer = None
            return False

    def stop_streaming_csv(self):
        try:
            if self.csv_file:
                self.csv_file.close()
                logger.info("Streaming CSV file closed.")
        except Exception:
            logger.warning("Error closing CSV file.")
    
    def save_to_csv(self, filename='kbid_auctions_data.csv'):
        """
        Save scraped data to CSV file
        
        Args:
            filename (str): Output CSV filename
            
        Returns:
            str: Filename if successful, None otherwise
        """
        if not self.all_items:
            logger.warning("No data to save!")
            return None
        
        logger.info(f"Saving {len(self.all_items)} items to {filename}...")
        
        # Define CSV headers (all fields)
        headers = [
            'lot_number',
            'item_title',
            'short_description',
            'current_bid',
            'next_required_bid',
            'high_bidder',
            'category',
            'item_closing_time',
            'item_url',
            'image_url',
            'auction_id',
            'auction_title',
            'affiliate',
            'location',
            'phone',
            'closing_date',
            'total_items',
            'categories',
            'auction_url'
        ]
        
        # Filter headers based on include_fields
        if self.include_fields:
            headers = [field for field in headers if field in self.include_fields]
        
        try:
            # Normalize filename into results directory if not absolute
            if not os.path.isabs(filename):
                filename = os.path.join(RESULTS_DIR, filename)
            os.makedirs(os.path.dirname(filename), exist_ok=True)

            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=headers, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(self.all_items)

            logger.info(f"Data successfully saved to {filename}")
            return filename

        except Exception as e:
            logger.error(f"Error saving CSV: {e}")
            return None
    
    def save_summary(self, filename=None):
        """
        Save a summary report of the scraping session
        
        Args:
            filename (str): Output text filename
        """
        try:
            if filename is None:
                filename = os.path.join(RESULTS_DIR, 'scraper_summary.txt')
            else:
                # ensure path is inside results dir if a plain filename was given
                if not os.path.isabs(filename):
                    filename = os.path.join(RESULTS_DIR, filename)

            with open(filename, 'w', encoding='utf-8') as f:
                f.write("K-BID AUCTION SCRAPER - SESSION SUMMARY\n")
                f.write("=" * 80 + "\n\n")
                f.write(f"Start Time: {self.stats['start_time'].strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"End Time: {self.stats['end_time'].strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Duration: {self.stats['end_time'] - self.stats['start_time']}\n\n")
                f.write(f"Auctions Found: {self.stats['auctions_found']}\n")
                f.write(f"Items Scraped: {self.stats['items_scraped']}\n")
                f.write(f"Errors: {self.stats['errors']}\n\n")
                f.write(f"Average Items per Auction: {self.stats['items_scraped'] / max(self.stats['auctions_found'], 1):.1f}\n")
            
            logger.info(f"[OK] Summary saved to {filename}")
            
        except Exception as e:
            logger.error(f"Error saving summary: {e}")


def main():
    """Main execution function"""
    print("\n" + "=" * 80)
    print("K-BID AUCTION SCRAPER")
    print("=" * 80)
    print("\nThis scraper will extract all live auction listings and item details")
    print("from k-bid.com and save them to a CSV file.\n")
    
    # Get user preferences
    try:
        delay = float(input("Enter delay between requests in seconds (default 1.0): ") or "1.0")
    except ValueError:
        delay = 1.0
        print(f"Invalid input, using default delay: {delay}s")
    
    output_file = input("Enter output CSV filename (default 'kbid_auctions_data.csv'): ").strip() or "kbid_auctions_data.csv"
    
    # Ensure .csv extension
    if not output_file.endswith('.csv'):
        output_file += '.csv'
    
    print("\nStarting scraper...\n")
    
    # Create and run scraper
    scraper = KBidScraper(delay=delay)

    # Install Ctrl+C handler to request graceful shutdown
    def _handle_sigint(sig, frame):
        logger.info('SIGINT received - requesting graceful stop...')
        scraper.stop_requested = True
        # Try to shut down any running executor
        try:
            if scraper.current_executor:
                scraper.current_executor.shutdown(wait=False)
        except Exception:
            pass
        # Close CSV to flush partial results
        try:
            scraper.stop_streaming_csv()
        except Exception:
            pass

    signal.signal(signal.SIGINT, _handle_sigint)

    # Start streaming CSV output (writes rows as they are scraped)
    started = scraper.start_streaming_csv(output_file)
    if not started:
        print(f"Could not open output file {output_file} for streaming. Exiting.")
        return

    try:
        scraper.scrape_all_auctions()
    except KeyboardInterrupt:
        # Fallback - should be handled by signal handler, but catch just in case
        logger.info('KeyboardInterrupt caught in main; shutting down')
        scraper.stop_requested = True
    finally:
        scraper.stop_streaming_csv()

    # Save summary
    scraper.save_summary()

    print(f"\n[OK] Complete! Data saved to: {output_file}")
    print(f"[OK] Summary saved to: {os.path.join(RESULTS_DIR, 'scraper_summary.txt')}")
    print(f"[OK] Log file: {os.path.join(RESULTS_DIR, 'kbid_scraper.log')}")


if __name__ == "__main__":
    main()