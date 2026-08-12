"""
K-Bid Auction Scraper - FIXED VERSION
======================================
This version properly extracts current bid prices and all other data
using the correct ID patterns found in K-Bid's HTML structure.

Key fixes:
1. Proper ID pattern matching: lot_current_bid_lot_k-bid_{auction_id}_{lot_id}
2. Robust bid extraction from listing pages
3. Better parsing logic that handles the actual HTML structure
4. Closing-time parsing: minutes_until_close + closing_status on every item

Usage (PowerShell):
  python scraper_enhanced.py

Author: Claude
Date: January 2026
"""

import cloudscraper
from bs4 import BeautifulSoup
import csv
import time
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlencode, urljoin, urlparse, parse_qsl, urlunparse
from datetime import datetime, timedelta, timezone
import logging
import sys
import os
import uuid
import math

try:
    import pgeocode
except ImportError:
    pgeocode = None

# Keep all generated runs at the workspace-level results root.
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
RESULTS_DIR = os.path.join(WORKSPACE_ROOT, 'results')
os.makedirs(RESULTS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class KBidScraperFixed:
    """Fixed K-Bid scraper with proper bid extraction"""

    SUPPORTED_DISTANCE_RADII = {10, 25, 50, 75, 100, 150, 250}
    
    def __init__(self, delay=1.0, item_workers=8, auction_workers=1, page_workers=4, retry_attempts=3, retry_backoff=0.5,
                 origin_zip=None, radius_miles=None, closing_date=None,
                 include_category_ids=None, exclude_category_ids=None,
                 exclude_lot_terms=None,
                 auction_category_ids=None, filter_listing_categories=False,
                 listing_max_hours=None, listing_min_hours=None,
                 results_root=None, run_dir=None, run_id=None):
        self.base_url = "https://www.k-bid.com"
        self.delay = delay
        self.item_workers = max(1, int(item_workers))
        self.auction_workers = max(1, int(auction_workers))
        self.page_workers = max(1, int(page_workers))
        self.retry_attempts = max(1, int(retry_attempts))
        self.retry_backoff = max(0, float(retry_backoff))
        self.origin_zip = str(origin_zip).strip() if origin_zip else None
        self.radius_miles = int(radius_miles) if radius_miles is not None else None
        if self.radius_miles is not None and self.radius_miles not in self.SUPPORTED_DISTANCE_RADII:
            raise ValueError(f"radius_miles must be one of {sorted(self.SUPPORTED_DISTANCE_RADII)}")
        if self.radius_miles is not None and not self.origin_zip:
            raise ValueError("origin_zip is required when radius_miles is set")
        self._zip_nom = pgeocode.Nominatim('us') if pgeocode and (self.origin_zip or self.radius_miles is not None) else None
        self._zip_coord_cache = {}
        self._origin_coords = self.lookup_zip_coords(self.origin_zip) if self.origin_zip else None
        self._location_filter_warned = False
        self.closing_date = self.normalize_filter_date(closing_date) if closing_date else None
        self.include_category_ids = self.normalize_category_ids(include_category_ids)
        self.exclude_category_ids = self.normalize_category_ids(exclude_category_ids)
        self.exclude_lot_terms = self.normalize_lot_terms(exclude_lot_terms)
        self.auction_category_ids = self.normalize_category_ids(auction_category_ids)
        self.filter_listing_categories = bool(filter_listing_categories)
        self.listing_max_seconds = int(float(listing_max_hours) * 3600) if listing_max_hours is not None else None
        self.listing_min_seconds = int(float(listing_min_hours) * 3600) if listing_min_hours is not None else None
        # cloudscraper transparently handles Cloudflare JS/cookie challenges.
        # It is a drop-in requests.Session replacement — all .get() calls work unchanged.
        self.session = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
        )
        self._thread_local = threading.local()
        self._thread_local.session = self.session
        self._stats_lock = threading.Lock()
        self._item_fetch_semaphore = threading.BoundedSemaphore(self.item_workers * self.page_workers)
        self.all_items = []
        self.stats = {
            'auctions_found': 0,
            'items_scraped': 0,
            'errors': 0,
            'closed_items_skipped': 0,
            'start_time': None,
            'end_time': None
        }
        # A caller can provide the canonical run layout. Standalone use keeps
        # a compatible unique directory beneath the workspace results root.
        results_root = os.path.abspath(results_root or RESULTS_DIR)
        cst = timezone(timedelta(hours=-6), name='CST')
        now_cst = datetime.now(cst)
        timestamp = now_cst.strftime('%a_%d_%b_%Y_%I-%M-%S_%z')
        self.run_id = run_id or f"run_{timestamp}_{uuid.uuid4().hex[:8]}"
        default_run_dir = os.path.join(results_root, 'runs', f'{now_cst:%Y}', f'{now_cst:%m}', self.run_id)
        self.run_dir = os.path.abspath(run_dir or default_run_dir)
        self.raw_dir = os.path.join(self.run_dir, 'raw')
        for child in ('raw', 'outputs', 'reports', 'logs', 'state', 'metadata'):
            os.makedirs(os.path.join(self.run_dir, child), exist_ok=True)
        logger.info(f"Run directory: {self.run_dir}")

    def get_session(self):
        """Return a Cloudscraper session scoped to the current thread."""
        session = getattr(self._thread_local, 'session', None)
        if session is None:
            session = cloudscraper.create_scraper(
                browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
            )
            self._thread_local.session = session
        return session

    def get_with_retry(self, url, timeout=15):
        """GET with a short exponential backoff for transient request failures."""
        last_error = None
        for attempt in range(1, self.retry_attempts + 1):
            try:
                response = self.get_session().get(url, timeout=timeout)
                response.raise_for_status()
                return response
            except Exception as e:
                last_error = e
                if attempt >= self.retry_attempts:
                    break
                sleep_for = self.retry_backoff * (2 ** (attempt - 1))
                logger.debug(f"Request failed ({attempt}/{self.retry_attempts}) for {url}: {e}; retrying in {sleep_for:.2f}s")
                time.sleep(sleep_for)
        raise last_error

    def build_auction_list_url(self, page_num=1):
        params = {'sort_field': 'end'}
        if page_num > 1:
            params['page'] = page_num
        if self.radius_miles is not None and self.origin_zip:
            params['distance_radius'] = int(self.radius_miles)
            params['distance_zip'] = self.origin_zip
        if self.closing_date:
            params['closing'] = self.closing_date.strftime('%Y-%m-%d')
            params['closing_mask'] = self.closing_date.strftime('%m/%d/%Y')
        query = urlencode(params)
        if self.filter_listing_categories:
            for category_id in sorted(self.auction_category_ids):
                query += f"&{urlencode({'auction_categories[]': category_id})}"

        url = f"{self.base_url}/auction/list"
        return f"{url}?{query}" if query else url

    def build_auction_page_url(self, auction_url, page_num):
        if page_num <= 1:
            return auction_url
        parsed = urlparse(auction_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query['page'] = str(page_num)
        return urlunparse(parsed._replace(query=urlencode(query)))

    def normalize_filter_date(self, value):
        """Normalize a K-Bid filter date from YYYY-MM-DD or MM/DD/YYYY."""
        text = str(value).strip()
        for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y'):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        raise ValueError("closing_date must be YYYY-MM-DD or MM/DD/YYYY")

    def normalize_category_ids(self, values):
        if values is None:
            return set()
        if isinstance(values, str):
            values = re.split(r'[,;\s]+', values.strip())
        return {str(value).strip() for value in values if str(value).strip()}

    def increment_stat(self, key, amount=1):
        with self._stats_lock:
            self.stats[key] += amount
    
    # ------------------------------------------------------------------
    # Closing-time helpers
    # ------------------------------------------------------------------

    # All date/time patterns seen on K-Bid item pages, ordered most→least specific
    _CLOSING_PATTERNS = [
        # "Sat, Jan 31, 2026 7:00pm CST"
        (r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[^,]*,\s*\w+\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}\s*(?:AM|PM)\s*[A-Z]{3}',
         '%a, %b %d, %Y %I:%M%p'),
        # "01/31/2026 7:00 PM"
        (r'\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}\s*(?:AM|PM)',
         '%m/%d/%Y %I:%M %p'),
        # "01/31/2026 19:00"
        (r'\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}',
         '%m/%d/%Y %H:%M'),
    ]

    def parse_closing_datetime(self, closing_time_str):
        """Parse item_closing_time string into a naive local datetime.

        Returns a datetime on success, None if unparseable.
        """
        if not closing_time_str or closing_time_str == 'N/A':
            return None
        # Strip timezone suffix before parsing (strptime can't handle CST/CDT)
        cleaned = re.sub(r'\s+[A-Z]{2,4}$', '', closing_time_str.strip())
        for pattern, fmt in self._CLOSING_PATTERNS:
            m = re.search(pattern, closing_time_str, re.I)
            if m:
                candidate = re.sub(r'\s+[A-Z]{2,4}$', '', m.group(0).strip())
                try:
                    return datetime.strptime(candidate, fmt)
                except ValueError:
                    continue
        # Last-resort: try the cleaned string directly against each format
        for _, fmt in self._CLOSING_PATTERNS:
            try:
                return datetime.strptime(cleaned, fmt)
            except ValueError:
                continue
        return None

    def compute_time_fields(self, item):
        """Add minutes_until_close and closing_status to an item dict in-place.

        closing_status values:
          'closing-soon'  — closes within 2 hours
          'today'         — closes within 24 hours
          'days-out'      — closes more than 24 hours away
          'unknown'       — could not parse closing time
        """
        closing_dt = self.parse_closing_datetime(item.get('item_closing_time', 'N/A'))
        if closing_dt is None:
            item['minutes_until_close'] = 'N/A'
            item['closing_status'] = 'unknown'
            return

        now = datetime.now()
        delta_minutes = (closing_dt - now).total_seconds() / 60

        # Already closed — treat as unknown so callers can filter if desired
        if delta_minutes < 0:
            item['minutes_until_close'] = 'N/A'
            item['closing_status'] = 'closed'
            return

        item['minutes_until_close'] = round(delta_minutes)
        if delta_minutes <= 120:
            item['closing_status'] = 'closing-soon'
        elif delta_minutes <= 1440:
            item['closing_status'] = 'today'
        else:
            item['closing_status'] = 'days-out'

    def is_visible_text_node(self, text_node):
        """Return True when a text node is not inside non-visible page code."""
        parent = text_node.find_parent() if text_node else None
        return bool(parent and parent.name not in {'script', 'style', 'noscript'})

    def extract_visible_location(self, soup):
        """Extract the auction location from visible auction detail text."""
        location_patterns = [
            re.compile(r'\bAuction\s+Location:\s*([^|]+?)(?:\s{2,}|Lot Categories:|Phone:|$)', re.I),
            re.compile(r'\bLocation:\s*([^|]+?)(?:\s{2,}|Lot Categories:|Phone:|$)', re.I),
            re.compile(r'\bAddress:\s*([^|]+?)(?:\s{2,}|Lot Categories:|Phone:|$)', re.I),
        ]

        for text_node in soup.find_all(string=re.compile(r'\b(?:Auction\s+Location|Location|Address):', re.I)):
            if not self.is_visible_text_node(text_node):
                continue
            parent = text_node.find_parent()
            text = parent.get_text(' ', strip=True) if parent else str(text_node).strip()
            if re.search(r'\bterms and conditions\b|\bi agree\b', text, re.I):
                continue
            for pattern in location_patterns:
                match = pattern.search(text)
                if match:
                    location = match.group(1).strip()
                    location = re.sub(r'\s+', ' ', location)
                    return self.clean_labelled_text(location, max_len=200)

        return "N/A"

    def extract_location_from_listing_card(self, card):
        """Extract address text from a K-Bid auction listing card."""
        icon = card.find('i', title=re.compile(r'^Location:', re.I))
        if icon and icon.parent:
            text = icon.parent.get_text(' ', strip=True)
            text = re.sub(r'^\s*Location:\s*', '', text, flags=re.I)
            return self.clean_labelled_text(text, max_len=200)

        for text_node in card.find_all(string=re.compile(r'\b\d{5}(?:-\d{4})?\b')):
            if self.is_visible_text_node(text_node):
                text = str(text_node).strip()
                if re.search(r'\b[A-Z]{2}\s+\d{5}(?:-\d{4})?\b', text):
                    return self.clean_labelled_text(text, max_len=200)

        return "N/A"

    def extract_zip(self, text):
        match = re.search(r'\b(\d{5})(?:-\d{4})?\b', str(text or ''))
        return match.group(1) if match else None

    def lookup_zip_coords(self, zip_code):
        if not zip_code:
            return None
        zip_code = str(zip_code).strip()[:5]
        if zip_code in self._zip_coord_cache:
            return self._zip_coord_cache[zip_code]
        if not self._zip_nom:
            return None
        result = self._zip_nom.query_postal_code(zip_code)
        lat = getattr(result, 'latitude', None)
        lon = getattr(result, 'longitude', None)
        if lat is None or lon is None or math.isnan(float(lat)) or math.isnan(float(lon)):
            coords = None
        else:
            coords = (float(lat), float(lon))
        self._zip_coord_cache[zip_code] = coords
        return coords

    def distance_miles(self, coord_a, coord_b):
        lat1, lon1 = map(math.radians, coord_a)
        lat2, lon2 = map(math.radians, coord_b)
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        hav = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return 3958.8 * 2 * math.asin(math.sqrt(hav))

    def listing_card_within_location_filter(self, card):
        """Return True when no radius filter is set or the card ZIP is within range."""
        if self.radius_miles is None:
            return True
        if not self.origin_zip or not self._origin_coords:
            if not self._location_filter_warned:
                logger.warning("Local radius check unavailable; relying on K-Bid distance_radius/distance_zip filter.")
                self._location_filter_warned = True
            return True

        location = self.extract_location_from_listing_card(card)
        auction_zip = self.extract_zip(location)
        if not auction_zip:
            logger.info(f"  Keeping auction with unknown ZIP for location filter: {location}")
            return True

        auction_coords = self.lookup_zip_coords(auction_zip)
        if not auction_coords:
            logger.info(f"  Keeping auction with unresolved ZIP for location filter: {location}")
            return True

        miles = self.distance_miles(self._origin_coords, auction_coords)
        return miles <= self.radius_miles

    def extract_category_id_from_href(self, href):
        match = re.search(r'[?&]category_ids=(\d+)', str(href or ''))
        return match.group(1) if match else None

    def extract_listing_card_category_links(self, card):
        """Return category-scoped auction URLs from a listing card."""
        links = []
        for link in card.find_all('a', href=re.compile(r'[?&]category_ids=\d+')):
            category_id = self.extract_category_id_from_href(link.get('href'))
            if not category_id:
                continue
            links.append({
                'category_id': category_id,
                'label': self.clean_labelled_text(link.get_text(' ', strip=True), max_len=120),
                'url': urljoin(self.base_url, link['href']),
            })
        return links

    def category_allowed(self, category_ids):
        ids = {str(category_id) for category_id in category_ids if str(category_id)}
        if self.include_category_ids and not ids.intersection(self.include_category_ids):
            return False
        if self.exclude_category_ids and ids.intersection(self.exclude_category_ids):
            return False
        return True

    @staticmethod
    def normalize_lot_terms(values):
        if not values:
            return tuple()
        if isinstance(values, str):
            values = values.replace(';', ',').split(',')
        return tuple(dict.fromkeys(str(value).strip().lower() for value in values if str(value).strip()))

    def lot_allowed(self, title, category):
        text = f"{title or ''} {category or ''}".lower()
        return not any(re.search(rf'(?<!\w){re.escape(term)}(?!\w)', text) for term in self.exclude_lot_terms)

    def extract_lot_categories(self, soup):
        """Extract category IDs and labels from an item detail page."""
        category_ids = []
        labels = []
        category_block = soup.find(id='lot_category')
        if not category_block:
            category_block = soup

        for link in category_block.find_all('a', href=re.compile(r'[?&]category_ids=\d+')):
            category_id = self.extract_category_id_from_href(link.get('href'))
            if category_id and category_id not in category_ids:
                category_ids.append(category_id)
            label = self.clean_labelled_text(link.get_text(' ', strip=True), max_len=100)
            if label != 'N/A':
                labels.append(label)

        return category_ids, labels

    def parse_countdown_seconds(self, text):
        """Parse K-Bid countdown text like '21h 18m 14s' into seconds."""
        if not text:
            return None

        total = 0
        found_unit = False
        for value, unit in re.findall(r'(\d+)\s*([wdhms])\b', str(text), re.I):
            found_unit = True
            amount = int(value)
            unit = unit.lower()
            if unit == 'w':
                total += amount * 604800
            elif unit == 'd':
                total += amount * 86400
            elif unit == 'h':
                total += amount * 3600
            elif unit == 'm':
                total += amount * 60
            elif unit == 's':
                total += amount

        return total if found_unit else None

    def is_active_auction_card(self, auction_card):
        """Return False when an auction list card timer is already at 0."""
        return self.get_auction_card_skip_reason(auction_card) is None

    def get_auction_card_skip_reason(self, auction_card):
        """Return a machine-readable reason when an auction listing card should be skipped."""
        timer = auction_card.find(class_=lambda value: value and 'auction-listing-timer' in value)
        if not timer:
            return None

        timer_text = timer.get_text(' ', strip=True)
        countdown_seconds = self.parse_countdown_seconds(timer_text)
        if countdown_seconds is not None and countdown_seconds <= 0:
            return 'zero-timer'
        if self.listing_min_seconds is not None and countdown_seconds is not None and countdown_seconds < self.listing_min_seconds:
            return 'before-listing-window'
        if self.listing_max_seconds is not None and countdown_seconds is not None and countdown_seconds > self.listing_max_seconds:
            return 'after-listing-window'
        if re.search(r'\b(?:closed|ended)\b', timer_text, re.I):
            return 'closed'
        return None

    def get_inactive_auction_urls_from_listing(self, soup):
        """Find auction URLs whose listing-card countdown is at zero."""
        inactive_urls = set()
        for timer in soup.find_all(class_=lambda value: value and 'auction-listing-timer' in value):
            auction_card = timer.find_parent('div', class_=re.compile(r'\brow\b'))
            if not auction_card or self.is_active_auction_card(auction_card):
                continue
            for link in auction_card.find_all('a', href=re.compile(r'/auction/\d+$')):
                inactive_urls.add(urljoin(self.base_url, link['href']))
        return inactive_urls

    def get_active_auction_links_from_listing(self, soup, log_skipped=False, include_countdowns=False):
        """Extract auction URLs from listing cards whose timer is above zero."""
        auctions = []
        seen = set()

        def append_auction(url, countdown_seconds):
            seen.add(url)
            auctions.append((url, countdown_seconds) if include_countdowns else url)

        cards = soup.find_all('div', class_=lambda value: value and 'panel-body' in value)
        for card in cards:
            timer = card.find(class_=lambda value: value and 'auction-listing-timer' in value)
            title = card.find(class_=lambda value: value and 'auction-title' in value)
            link = title.find('a', href=re.compile(r'/auction/\d+$')) if title else None
            if not timer or not link:
                continue

            auction_url = urljoin(self.base_url, link['href'])
            if auction_url in seen:
                continue
            countdown_seconds = self.parse_countdown_seconds(timer.get_text(' ', strip=True))

            skip_reason = self.get_auction_card_skip_reason(card)
            if skip_reason:
                if log_skipped:
                    countdown = timer.get_text(' ', strip=True)
                    if skip_reason == 'zero-timer':
                        logger.info(f"  Skipping auction with zero timer: {auction_url} ({countdown})")
                    elif skip_reason == 'after-listing-window':
                        logger.info(f"  Skipping auction outside listing max-hours window: {auction_url} ({countdown})")
                    elif skip_reason == 'before-listing-window':
                        logger.info(f"  Skipping auction before listing min-hours window: {auction_url} ({countdown})")
                    else:
                        logger.info(f"  Skipping auction listing ({skip_reason}): {auction_url} ({countdown})")
                continue
            if not self.listing_card_within_location_filter(card):
                if log_skipped:
                    location = self.extract_location_from_listing_card(card)
                    logger.info(f"  Skipping auction outside {self.radius_miles:g} miles of {self.origin_zip}: {auction_url} ({location})")
                continue

            category_links = self.extract_listing_card_category_links(card)
            if self.filter_listing_categories and self.include_category_ids:
                scoped_urls = []
                for category_link in category_links:
                    category_id = category_link['category_id']
                    if self.category_allowed([category_id]) and category_link['url'] not in seen:
                        scoped_urls.append(category_link['url'])
                if not scoped_urls:
                    if log_skipped:
                        logger.debug(f"  Skipping auction without included categories: {auction_url}")
                    continue
                for scoped_url in scoped_urls:
                    append_auction(scoped_url, countdown_seconds)
                continue

            card_category_ids = [category_link['category_id'] for category_link in category_links]
            if self.filter_listing_categories and card_category_ids and not self.category_allowed(card_category_ids):
                if log_skipped:
                    logger.debug(f"  Skipping auction with only excluded categories: {auction_url}")
                continue

            append_auction(auction_url, countdown_seconds)

        if auctions or cards:
            return auctions

        inactive_urls = self.get_inactive_auction_urls_from_listing(soup)
        for link in soup.find_all('a', href=re.compile(r'/auction/\d+$')):
            auction_url = urljoin(self.base_url, link['href'])
            if auction_url in seen:
                continue
            if auction_url in inactive_urls:
                if log_skipped:
                    logger.info(f"  Skipping auction with zero timer: {auction_url}")
                continue
            append_auction(auction_url, None)

        return auctions

    def parse_money(self, text):
        """Parse money string to decimal format"""
        if not text:
            return "0.00"
        try:
            # Remove currency symbols and whitespace
            cleaned = re.sub(r'[$£€,\s]', '', str(text))
            # Extract first number found
            match = re.search(r'(\d+\.?\d*)', cleaned)
            if match:
                return f"{float(match.group(1)):.2f}"
            return "0.00"
        except (ValueError, AttributeError):
            return "0.00"

    def clean_labelled_text(self, text, max_len=200):
        """Clean text by removing common leading labels (e.g., 'Lot Description:', 'Description:',
        'Affiliate:', 'Location:', etc.), collapsing whitespace, and trimming to max_len.

        Returns 'N/A' if input is falsy.
        """
        if not text:
            return "N/A"
        try:
            raw = str(text).strip()
            # Remove common leading labels (with or without colon), case-insensitive
            cleaned = re.sub(r'^(?:Lot\s+Description:?|Description:?|Affiliate:?|Auctioneer:?|Location:?|Address:?|Phone:?|Lot:?|Click for Details:?|Item:?)\s*', '', raw, flags=re.I)
            # Remove stray label-like prefixes that may appear mid-string (e.g., 'Lot Description: Foo')
            # but prefer only leading labels to avoid removing meaningful content.
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()
            if not cleaned:
                return "N/A"
            return cleaned[:max_len]
        except Exception:
            return "N/A"
    
    def extract_ids_from_element_id(self, element_id):
        """
        Extract auction_id and lot_id from K-Bid element ID pattern
        Pattern: lot_current_bid_lot_k-bid_{auction_id}_{lot_id}
        """
        if not element_id:
            return None, None
        match = re.search(r'lot_k-bid[_-](\d+)[_-](\d+)', element_id)
        if match:
            return match.group(1), match.group(2)
        return None, None
    
    def find_bid_element(self, soup, pattern_base='lot_current_bid_lot_k-bid'):
        """
        Find bid element by ID pattern
        Pattern: lot_current_bid_lot_k-bid_{auction_id}_{lot_id}
        """
        # Look for elements with IDs matching the pattern
        elements = soup.find_all(id=re.compile(f'{pattern_base}[_-]\\d+[_-]\\d+'))
        return elements[0] if elements else None
    
    def fetch_item_details_from_page(self, item_url):
        """
        Fetch an individual item page and extract bid details
        
        Args:
            item_url: URL of the item detail page
            
        Returns:
            dict: Item details (current_bid, next_required_bid, high_bidder, etc.)
        """
        details = {
            'current_bid': '0.00',
            'next_required_bid': 'N/A',
            'high_bidder': 'No bids',
            'category': 'N/A',
            'image_url': 'N/A',
            'item_closing_time': 'N/A',
            'short_description': 'N/A',
            # Indicates whether the lot is currently open for bidding
            'is_open': True
        }
        
        try:
            with self._item_fetch_semaphore:
                response = self.get_with_retry(item_url, timeout=15)
            soup = BeautifulSoup(response.content, 'lxml')
            
            # Extract current bid using ID pattern
            bid_elem = self.find_bid_element(soup, 'lot_current_bid_lot_k-bid')
            if bid_elem:
                bid_text = bid_elem.get_text(strip=True)
                details['current_bid'] = self.parse_money(bid_text)
                logger.debug(f"Found current bid: {bid_text} -> {details['current_bid']}")
            
            # Extract next required bid
            next_elem = self.find_bid_element(soup, 'lot_next_required_bid_lot_k-bid')
            if next_elem:
                next_text = next_elem.get_text(strip=True)
                details['next_required_bid'] = self.parse_money(next_text)
            
            # Extract high bidder
            bidder_elem = self.find_bid_element(soup, 'lot_current_high_bidder_detail_lot_k-bid')
            if bidder_elem:
                bidder_text = bidder_elem.get_text(strip=True)
                details['high_bidder'] = bidder_text.replace('High Bidder:', '').strip()
            
            # Extract category
            category_ids, category_labels = self.extract_lot_categories(soup)
            details['category_ids'] = ','.join(category_ids) if category_ids else 'N/A'
            if category_labels:
                details['category'] = ' > '.join(category_labels)
            else:
                category_elem = soup.find('a', href=re.compile(r'category_ids='))
                if category_elem:
                    details['category'] = self.clean_labelled_text(category_elem.get_text(strip=True), max_len=100)

            if category_ids and not self.category_allowed(category_ids):
                details['is_open'] = False
                details['skip_reason'] = 'category-filter'
                return details
            
            # Extract image - skip logos, get actual item images
            img_elem = soup.find('img', src=True)
            if img_elem and img_elem.get('src'):
                img_url = img_elem['src']
                # Skip logo images - look for item images in specific locations
                if 'site_logo' not in img_url and 'logo' not in img_url.lower():
                    if not img_url.startswith('http'):
                        img_url = urljoin(self.base_url, img_url)
                    details['image_url'] = img_url
                else:
                    # Try to find image in galleria or item image container
                    item_img = soup.find('img', class_=re.compile(r'galleria|item.*image', re.I))
                    if not item_img:
                        # Look for images in kpi-auction-images S3 bucket
                        item_img = soup.find('img', src=re.compile(r'kpi-auction-images'))
                    if item_img and item_img.get('src'):
                        img_url = item_img['src']
                        if not img_url.startswith('http'):
                            img_url = urljoin(self.base_url, img_url)
                        details['image_url'] = img_url
            
            # Extract closing time - clean up the format
            closing_elem = soup.find(string=re.compile(r'Closes|Closing', re.I))
            if closing_elem:
                closing_parent = closing_elem.find_parent()
                if closing_parent:
                    closing_text = closing_parent.get_text(strip=True)
                    # Extract date/time patterns like "Sat, Jan 31, 2026 7:00pm CST"
                    time_match = re.search(r'((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[^,]*,\s*\w+\s+\d+,\s+\d{4}\s+\d{1,2}:\d{2}\s*(?:AM|PM)?\s*[A-Z]{3})', closing_text, re.I)
                    if not time_match:
                        # Try simpler pattern: "1/31/2026 7:00 PM"
                        time_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}\s*(?:AM|PM)?(?:\s*[A-Z]{3})?)', closing_text, re.I)
                    if time_match:
                        details['item_closing_time'] = time_match.group(1).strip()
                    else:
                        # Fallback: clean up common artifacts
                        cleaned = closing_text.replace('Closes:', '').replace('Begins Closing In:', '').replace('No Connection!', '').strip()
                        # Remove countdown timers (format: 18:20:20)
                        cleaned = re.sub(r'\d{1,2}:\d{2}:\d{2}', '', cleaned).strip()
                        if cleaned:
                            details['item_closing_time'] = cleaned
            
            # Extract description and remove common labels like 'Lot Description:'
            desc_elem = soup.find('div', class_=re.compile(r'lot.*desc', re.I))
            if desc_elem:
                raw_desc = desc_elem.get_text(separator=' ', strip=True)
                details['short_description'] = self.clean_labelled_text(raw_desc, max_len=200)

            # --- Determine open/closed status ---
            # If the page contains clear indicators the lot has been sold/closed/ended,
            # mark it as closed. Otherwise prefer presence of bidding controls to mark open.
            closed_indicators = re.compile(r"\b(Sold(?: to)?|Winner|Closed|Ended|Bidding closed|Lot Closed|This lot has ended|Auction Ended|Sold for)\b", re.I)
            has_closed_text = soup.find(string=closed_indicators)

            # Look for actionable bid buttons/links that indicate the lot is open
            bid_action = soup.find(['button', 'a'], string=re.compile(r'(Place Bid|Bid Now|Start Bidding|Place a Bid|Bid)', re.I))

            if has_closed_text and not bid_action:
                details['is_open'] = False
            else:
                closing_dt = self.parse_closing_datetime(details.get('item_closing_time', 'N/A'))
                if closing_dt is not None and closing_dt < datetime.now():
                    details['is_open'] = False
                # default remains True unless clear closed indicators found
                details['is_open'] = details.get('is_open', True)
                
        except Exception as e:
            logger.warning(f"Error fetching item details from {item_url}: {e}")
        
        return details
    
    def extract_item_from_container(self, container, auction_info):
        """
        Extract item details from a container element (listing page or item page)
        
        Args:
            container: BeautifulSoup element containing item info
            auction_info: Dict with auction metadata
            
        Returns:
            dict: Item details
        """
        item = auction_info.copy()
        
        # Extract lot number from URL or text
        lot_number = "N/A"
        lot_link = container.find('a', href=re.compile(r'/item/(\d+)'))
        if lot_link and lot_link.get('href'):
            url_match = re.search(r'/item/(\d+)', lot_link['href'])
            if url_match:
                lot_number = url_match.group(1)
                item['item_url'] = urljoin(self.base_url, lot_link['href'])
        
        # Try to extract from text if URL method failed
        if lot_number == "N/A":
            lot_text = container.get_text()
            lot_match = re.search(r'Lot:\s*(\d+\w*)', lot_text, re.I)
            if lot_match:
                lot_number = lot_match.group(1)
        
        item['lot_number'] = lot_number
        
        # Extract title
        title_elem = container.find(['h2', 'h3', 'h4', 'h5'])
        if not title_elem:
            link_candidate = container.find('a', href=re.compile(r'/item/'))
            if link_candidate and link_candidate.get_text(strip=True):
                title_text = link_candidate.get_text(strip=True)
                if 'Click for Details' not in title_text and 'Lot:' not in title_text:
                    title_elem = link_candidate
        
        item['item_title'] = self.clean_labelled_text(title_elem.get_text(strip=True)) if title_elem else "N/A"
        
        # ===== CRITICAL FIX: Fetch item detail page to get accurate bid data =====
        # The listing page containers don't have the bid ID elements - they only exist on item pages
        if item.get('item_url') and item['item_url'] != "N/A":
            logger.debug(f"Fetching details for lot {lot_number} from item page...")
            details = self.fetch_item_details_from_page(item['item_url'])
            # Skip closed and category-filtered items.
            if details is None or details.get('is_open') is False:
                reason = details.get('skip_reason') if details else None
                if reason == 'category-filter':
                    logger.info(f"    Skipping category-filtered lot {lot_number} ({item.get('item_url')})")
                else:
                    logger.info(f"    Skipping closed/ended lot {lot_number} ({item.get('item_url')})")
                    try:
                        self.increment_stat('closed_items_skipped')
                    except Exception:
                        pass
                return None
            item.update(details)
            if not self.lot_allowed(item.get('item_title'), item.get('category')):
                logger.info(f"    Skipping excluded furniture/appliance lot {lot_number} ({item.get('item_url')})")
                return None
        else:
            # Fallback values if no item URL
            item['short_description'] = "N/A"
            item['current_bid'] = "0.00"
            item['next_required_bid'] = "N/A"
            item['high_bidder'] = "No bids"
            item['category'] = "N/A"
            item['image_url'] = "N/A"
            item['item_closing_time'] = "N/A"

        # Compute time-to-close fields now that item_closing_time is populated
        self.compute_time_fields(item)

        return item
    
    def get_auction_details(self, auction_url):
        """
        Get basic auction information
        
        Args:
            auction_url: URL of the auction
            
        Returns:
            dict: Auction information
        """
        logger.info(f"Fetching auction details: {auction_url}")
        
        try:
            response = self.get_with_retry(auction_url, timeout=15)
            soup = BeautifulSoup(response.content, 'lxml')
            
            # Extract auction ID from URL
            auction_id = "N/A"
            match = re.search(r'/auction/(\d+)', auction_url)
            if match:
                auction_id = match.group(1)
            
            # Extract auction title
            title_elem = soup.find('h1') or soup.find('h2', class_=re.compile(r'auction.*title', re.I))
            auction_title = self.clean_labelled_text(title_elem.get_text(strip=True), max_len=200) if title_elem else "N/A"
            
            # Extract affiliate/auctioneer - avoid JavaScript code
            affiliate = "N/A"
            affiliate_elem = soup.find(string=re.compile(r'Affiliate|Auctioneer', re.I))
            if affiliate_elem:
                parent = affiliate_elem.find_parent()
                if parent:
                    affiliate_text = parent.get_text(strip=True)
                    # Skip if it looks like JavaScript
                    if 'let ' not in affiliate_text and 'var ' not in affiliate_text and 'function' not in affiliate_text:
                        affiliate = affiliate_text.replace('Affiliate:', '').replace('Auctioneer:', '').strip()
                        # Take only the first line if multiple lines
                        if '\n' in affiliate:
                            affiliate = affiliate.split('\n')[0].strip()
            # Clean affiliate labels
            affiliate = self.clean_labelled_text(affiliate, max_len=100)
            
            # Extract location and phone - parse more carefully
            location = self.extract_visible_location(soup)
            phone = "N/A"
            location_elem = soup.find(
                string=lambda text: (
                    text
                    and self.is_visible_text_node(text)
                    and re.search(r'\b(?:Auction\s+Location|Location|Address):', text, re.I)
                )
            )
            if location == "N/A" and location_elem:
                parent = location_elem.find_parent()
                if parent:
                    location_text = parent.get_text(' ', strip=True)
                    # Remove "Location:" prefix
                    location_text = re.sub(r'\bAuction\s+Location:\s*|\bLocation:\s*|\bAddress:\s*', '', location_text, flags=re.I).strip()
                    # Extract phone number if present
                    phone_match = re.search(r'Phone:\s*([\d\-\(\)\s]+)', location_text)
                    if phone_match:
                        phone = phone_match.group(1).strip()
                        # Remove phone from location
                        location_text = location_text.replace(phone_match.group(0), '').strip()
                    # Extract address before "Phone:" or "Lot Categories"
                    if 'Phone:' in location_text:
                        location = location_text.split('Phone:')[0].strip()
                    elif 'Lot Categories:' in location_text:
                        location = location_text.split('Lot Categories:')[0].strip()
                    else:
                        # Take first reasonable chunk (before excessive content)
                        lines = location_text.split('\n')
                        if lines:
                            location = lines[0].strip()
                        else:
                            # Limit to first 100 chars to avoid huge blocks
                            location = location_text[:100].strip()
            # Clean location labels
            location = self.clean_labelled_text(location, max_len=200)

            visible_text = soup.get_text(' ', strip=True)
            premium_match = re.search(r"Buyer'?s?\s+Premium(?:\s+Cap)?\s*:?\s*(\d+(?:\.\d+)?)\s*%\s*(?:\$([\d,]+(?:\.\d+)?))?", visible_text, re.I)
            buyers_premium_rate = round(float(premium_match.group(1)) / 100, 6) if premium_match else "N/A"
            buyers_premium_cap = float(premium_match.group(2).replace(',', '')) if premium_match and premium_match.group(2) else "N/A"
            tax_match = re.search(r"(?:Sales\s+Tax|Tax\s+Rate)\s*:?\s*(\d+(?:\.\d+)?)\s*%", visible_text, re.I)
            sales_tax_rate = round(float(tax_match.group(1)) / 100, 6) if tax_match else "N/A"
            
            # Extract closing date - avoid terms & conditions
            closing_date = "N/A"
            closing_elem = soup.find(string=re.compile(r'Closing\s*Date|Ends|Auction\s*Ends', re.I))
            if closing_elem:
                parent = closing_elem.find_parent()
                if parent:
                    closing_text = parent.get_text(strip=True)
                    # Skip if it's terms/conditions text
                    if 'Inspection' not in closing_text and 'Bidders are' not in closing_text:
                        # Look for date patterns
                        date_match = re.search(r'((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[^,]*,\s*\w+\s+\d+,\s+\d{4}\s+\d{1,2}:\d{2}\s*(?:AM|PM)?\s*[A-Z]{3})', closing_text, re.I)
                        if not date_match:
                            date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}\s*(?:AM|PM)?)', closing_text, re.I)
                        if date_match:
                            closing_date = date_match.group(1).strip()
                        else:
                            # Clean up and use first line
                            closing_date = closing_text.replace('Closing Date:', '').replace('Ends:', '').strip()
                            if '\n' in closing_date:
                                closing_date = closing_date.split('\n')[0].strip()
                            # Limit length
                            if len(closing_date) > 50:
                                closing_date = closing_date[:50].strip()
            
            # Count total items
            total_items = 0
            item_links = soup.find_all('a', href=re.compile(r'/item/\d+'))
            total_items = len(set([link['href'] for link in item_links]))
            
            auction_info = {
                'auction_id': auction_id,
                'auction_title': auction_title,
                'auction_url': auction_url,
                'affiliate': affiliate,
                'location': location,
                'buyers_premium_rate': buyers_premium_rate,
                'buyers_premium_cap': buyers_premium_cap,
                'sales_tax_rate': sales_tax_rate,
                'phone': phone,
                'closing_date': closing_date,
                'total_items': str(total_items),
                'categories': "N/A"
            }
            
            logger.info(f"  Auction ID: {auction_id}, Title: {auction_title}")
            return auction_info
            
        except Exception as e:
            logger.error(f"Error getting auction details: {e}")
            return {
                'auction_id': 'N/A',
                'auction_title': 'N/A',
                'auction_url': auction_url,
                'affiliate': 'N/A',
                'location': 'N/A',
                'buyers_premium_rate': 'N/A',
                'buyers_premium_cap': 'N/A',
                'sales_tax_rate': 'N/A',
                'phone': 'N/A',
                'closing_date': 'N/A',
                'total_items': '0',
                'categories': 'N/A'
            }

    def extract_lot_containers(self, soup):
        lot_containers = []
        lot_headings = soup.find_all(['h4', 'h5', 'h3'], string=re.compile(r'Lot:\s*\d+', re.I))

        for heading in lot_headings:
            container = heading.find_parent(['div', 'article', 'section'])
            if container:
                lot_containers.append(container)

        if not lot_containers:
            item_links = soup.find_all('a', href=re.compile(r'/item/\d+'))
            seen = set()
            for link in item_links:
                parent = link.find_parent(['div', 'article', 'section'])
                if parent and id(parent) not in seen:
                    seen.add(id(parent))
                    lot_containers.append(parent)

        unique_containers = []
        seen_container_urls = set()
        for container in lot_containers:
            lot_link = container.find('a', href=re.compile(r'/item/\d+'))
            item_url = urljoin(self.base_url, lot_link['href']) if lot_link and lot_link.get('href') else None
            if item_url and item_url in seen_container_urls:
                continue
            if item_url:
                seen_container_urls.add(item_url)
            unique_containers.append(container)

        return unique_containers

    def discover_auction_page_numbers(self, soup):
        page_numbers = {1}
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            parsed = urlparse(urljoin(self.base_url, href))
            query = dict(parse_qsl(parsed.query, keep_blank_values=True))
            page_value = query.get('page')
            if page_value and str(page_value).isdigit():
                page_numbers.add(int(page_value))

        for text in soup.find_all(string=re.compile(r'^\s*\d+\s*$')):
            parent = text.find_parent('a')
            if parent:
                try:
                    page_numbers.add(int(str(text).strip()))
                except ValueError:
                    pass

        return sorted(page_numbers)

    def extract_items_from_auction_page(self, page_url, page_num, auction_info):
        logger.info(f"  Scraping page {page_num}: {page_url}")
        response = self.get_with_retry(page_url, timeout=15)
        soup = BeautifulSoup(response.content, 'lxml')
        lot_containers = self.extract_lot_containers(soup)

        if not lot_containers:
            logger.info(f"  No items found on page {page_num}")
            return [], soup

        logger.info(f"  Found {len(lot_containers)} unique item containers on page {page_num}")
        page_items = []
        max_workers = min(self.item_workers, len(lot_containers))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(self.extract_item_from_container, container, auction_info)
                for container in lot_containers
            ]

            for future in as_completed(futures):
                try:
                    item = future.result()
                except Exception as e:
                    logger.warning(f"    Error extracting item: {e}")
                    self.increment_stat('errors')
                    continue
                if item and item.get('lot_number') != "N/A":
                    page_items.append(item)

        return page_items, soup
    
    def scrape_auction_items(self, auction_url, max_items=None):
        """
        Scrape all items from an auction
        
        Args:
            auction_url: URL of the auction
            max_items: optional int, stop after this many items have been collected
            
        Returns:
            list: List of item dictionaries
        """
        # Get auction info
        auction_info = self.get_auction_details(auction_url)
        items = []
        seen_items = set()

        def add_page_items(page_items):
            for item in page_items:
                item_url = item.get('item_url', 'N/A')
                if item_url != 'N/A' and item_url in seen_items:
                    logger.debug(f"    Skipping duplicate: {item_url}")
                    continue
                seen_items.add(item_url)
                items.append(item)
                self.increment_stat('items_scraped')
                logger.debug(f"    Extracted lot {item.get('lot_number')}: {item.get('item_title')[:50]}")
                if max_items is not None and len(items) >= max_items:
                    return True
            return False

        try:
            first_page_url = self.build_auction_page_url(auction_url, 1)
            first_page_items, first_page_soup = self.extract_items_from_auction_page(first_page_url, 1, auction_info)
            if add_page_items(first_page_items):
                logger.info(f"  Reached max_items limit: {max_items}")
                return items[:max_items]

            page_numbers = self.discover_auction_page_numbers(first_page_soup)
            remaining_pages = [page_num for page_num in page_numbers if page_num > 1]
            if not remaining_pages:
                logger.info(f"  No more pages for this auction")
            else:
                logger.info(f"  Discovered {len(page_numbers)} auction pages; scraping {len(remaining_pages)} remaining pages with {min(self.page_workers, len(remaining_pages))} page workers")
                max_workers = min(self.page_workers, len(remaining_pages))
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_to_page = {
                        executor.submit(
                            self.extract_items_from_auction_page,
                            self.build_auction_page_url(auction_url, page_num),
                            page_num,
                            auction_info
                        ): page_num
                        for page_num in remaining_pages
                    }
                    for future in as_completed(future_to_page):
                        page_num = future_to_page[future]
                        try:
                            page_items, _ = future.result()
                        except Exception as e:
                            logger.error(f"  Error on page {page_num}: {e}")
                            self.increment_stat('errors')
                            continue
                        if add_page_items(page_items):
                            logger.info(f"  Reached max_items limit: {max_items}")
                            return items[:max_items]
        except Exception as e:
            logger.error(f"  Error scraping auction {auction_url}: {e}")
            self.increment_stat('errors')
        
        logger.info(f"  Total items from auction: {len(items)}")
        return items
    
    def get_auction_list_pages(self):
        """Get all auction listing page URLs"""
        logger.info("Fetching auction list pages...")
        pages = []
        page_num = 1
        
        while True:
            url = self.build_auction_list_url(page_num)
            
            try:
                response = self.get_with_retry(url, timeout=15)
                soup = BeautifulSoup(response.content, 'lxml')
                
                auction_links = self.get_active_auction_links_from_listing(soup)
                listing_cards = soup.find_all('div', class_=lambda value: value and 'panel-body' in value)
                
                if not auction_links and not listing_cards:
                    break
                
                pages.append(url)
                logger.info(f"Found auction listing page {page_num}")
                
                next_link = soup.find('a', string='Next »')
                if not next_link:
                    break
                
                page_num += 1
                time.sleep(self.delay)
                
            except Exception as e:
                logger.error(f"Error fetching page {page_num}: {e}")
                break
        
        logger.info(f"Total listing pages: {len(pages)}")
        return pages
    
    def get_auctions_from_page(self, page_url):
        """Extract auction URLs from a listing page"""
        return [url for url, _ in self.get_auction_candidates_from_page(page_url)]

    def get_auction_candidates_from_page(self, page_url):
        """Extract active auction URLs and listing countdown seconds."""
        logger.info(f"Extracting auctions from: {page_url}")
        candidates = []
        
        try:
            response = self.get_with_retry(page_url, timeout=15)
            soup = BeautifulSoup(response.content, 'lxml')
            
            auction_links = self.get_active_auction_links_from_listing(
                soup, log_skipped=True, include_countdowns=True
            )
            
            seen = set()
            for auction_url, countdown_seconds in auction_links:
                if auction_url not in seen:
                    seen.add(auction_url)
                    candidates.append((auction_url, countdown_seconds))
            
            logger.info(f"  Found {len(candidates)} unique auctions")
            
        except Exception as e:
            logger.error(f"Error extracting auctions: {e}")
        
        return candidates
    
    def scrape_all_auctions(self):
        """Main scraping method"""
        self.stats['start_time'] = datetime.now()
        logger.info("=" * 80)
        logger.info("Starting K-Bid Auction Scraper (FIXED VERSION)")
        logger.info("=" * 80)
        
        # Get all listing pages
        list_pages = self.get_auction_list_pages()
        
        # Extract auctions from all pages
        all_auction_urls = []
        for page_url in list_pages:
            auctions = self.get_auctions_from_page(page_url)
            all_auction_urls.extend(auctions)
            time.sleep(self.delay)
        
        # Remove duplicates
        all_auction_urls = list(set(all_auction_urls))
        self.stats['auctions_found'] = len(all_auction_urls)
        
        logger.info(f"\nFound {len(all_auction_urls)} total auctions to scrape")
        
        # Scrape each auction
        if self.auction_workers <= 1:
            for i, auction_url in enumerate(all_auction_urls, 1):
                logger.info(f"\n[{i}/{len(all_auction_urls)}] Scraping auction: {auction_url}")
                items = self.scrape_auction_items(auction_url)
                self.all_items.extend(items)
                time.sleep(self.delay)
        else:
            max_workers = min(self.auction_workers, len(all_auction_urls))
            logger.info(f"Scraping auctions with {max_workers} auction workers")
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_url = {
                    executor.submit(self.scrape_auction_items, auction_url): auction_url
                    for auction_url in all_auction_urls
                }
                for i, future in enumerate(as_completed(future_to_url), 1):
                    auction_url = future_to_url[future]
                    try:
                        items = future.result()
                        self.all_items.extend(items)
                        logger.info(f"[{i}/{len(all_auction_urls)}] Finished auction: {auction_url} ({len(items)} items)")
                    except Exception as e:
                        logger.error(f"[{i}/{len(all_auction_urls)}] Error scraping auction {auction_url}: {e}")
                        self.increment_stat('errors')
        
        self.stats['end_time'] = datetime.now()
        
        # Print summary
        logger.info("\n" + "=" * 80)
        logger.info("SCRAPING COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Auctions scraped: {self.stats['auctions_found']}")
        logger.info(f"Items collected: {self.stats['items_scraped']}")
        logger.info(f"Errors: {self.stats['errors']}")
        logger.info(f"Duration: {self.stats['end_time'] - self.stats['start_time']}")
        
        return self.all_items
    
    def save_to_csv(self, filename='kbid_auctions_data.csv'):
        """Save data to CSV"""
        if not self.all_items:
            logger.warning("No data to save!")
            return None
        
        filename = filename if os.path.isabs(filename) else os.path.join(self.raw_dir, os.path.basename(filename))
        logger.info(f"Saving {len(self.all_items)} items to {filename}...")
        
        # Column order: Logical flow from item details → money → time → links → metadata
        headers = [
            'lot_number', 'auction_title', 'item_title', 'short_description',
            'current_bid', 'next_required_bid', 'high_bidder',
            'buyers_premium_rate', 'buyers_premium_cap', 'sales_tax_rate',
            'category', 'category_ids',
            'item_closing_time', 'minutes_until_close', 'closing_status',
            'closing_date', 'item_url',
            'auction_id', 'auction_url', 'location'
        ]
        
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=headers, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(self.all_items)
            
            logger.info(f"Data saved to {filename}")
            return filename
        except Exception as e:
            logger.error(f"Error saving CSV: {e}")
            return None


def main():
    """Main execution"""
    print("\n" + "=" * 80)
    print("K-BID AUCTION SCRAPER - FIXED VERSION")
    print("=" * 80)
    print("\nThis version properly extracts current bid prices!")
    print("It uses the correct ID patterns from K-Bid's HTML structure.\n")
    
    try:
        delay = float(input("Enter delay between requests in seconds (default 1.0): ") or "1.0")
    except ValueError:
        delay = 1.0
    
    output_file = input("Enter output CSV filename (default 'kbid_auctions_data.csv'): ").strip() or "kbid_auctions_data.csv"
    if not output_file.endswith('.csv'):
        output_file += '.csv'
    
    print("\nStarting scraper...\n")
    
    scraper = KBidScraperFixed(delay=delay)
    scraper.scrape_all_auctions()
    scraper.save_to_csv(output_file)
    
    print(f"\n{'=' * 80}")
    print("COMPLETE!")
    print(f"{'=' * 80}")
    print(f"Data saved to: {scraper.run_dir}")
    print(f"Total items: {len(scraper.all_items)}")
    print(f"Check the log file for details: {os.path.join(RESULTS_DIR, 'kbid_scraper.log')}")


if __name__ == "__main__":
    main()
