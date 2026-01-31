"""
K-Bid Auction Scraper - FIXED VERSION
======================================
This version properly extracts current bid prices and all other data
using the correct ID patterns found in K-Bid's HTML structure.

Key fixes:
1. Proper ID pattern matching: lot_current_bid_lot_k-bid_{auction_id}_{lot_id}
2. Robust bid extraction from listing pages
3. Better parsing logic that handles the actual HTML structure

Author: Claude
Date: January 2026
"""

import requests
from bs4 import BeautifulSoup
import csv
import time
import re
from urllib.parse import urljoin
from datetime import datetime
import logging
import sys
import os
import uuid

# Ensure results directory exists
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


class KBidScraperFixed:
    """Fixed K-Bid scraper with proper bid extraction"""
    
    def __init__(self, delay=1.0):
        self.base_url = "https://www.k-bid.com"
        self.delay = delay
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
            'closed_items_skipped': 0,
            'start_time': None,
            'end_time': None
        }
        # Create unique run directory
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.run_id = f"run_{ts}_{str(uuid.uuid4())[:8]}"
        self.run_dir = os.path.join(RESULTS_DIR, self.run_id)
        os.makedirs(self.run_dir, exist_ok=True)
        logger.info(f"Run directory: {self.run_dir}")
    
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
            response = self.session.get(item_url, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
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
            category_elem = soup.find('a', href=re.compile(r'category_ids='))
            if category_elem:
                details['category'] = self.clean_labelled_text(category_elem.get_text(strip=True), max_len=100)
            
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
                # If there's no explicit closed text but also no bid actions and the closing
                # time appears to be in the past, we can conservatively mark closed.
                if not bid_action:
                    # Try to interpret item_closing_time if present (best-effort)
                    try:
                        ct = details.get('item_closing_time')
                        if ct and ct != 'N/A':
                            # A simple heuristic: if the text contains year and time, parse it
                            dt_match = re.search(r'\d{4}', ct)
                            if dt_match:
                                # If parsing fails, assume it's still open (do not block)
                                pass
                    except Exception:
                        pass
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
            # Skip closed items
            if details is None or details.get('is_open') is False:
                logger.info(f"    Skipping closed/ended lot {lot_number} ({item.get('item_url')})")
                # update stats for skipped closed items
                try:
                    self.stats['closed_items_skipped'] += 1
                except Exception:
                    pass
                return None
            item.update(details)
        else:
            # Fallback values if no item URL
            item['short_description'] = "N/A"
            item['current_bid'] = "0.00"
            item['next_required_bid'] = "N/A"
            item['high_bidder'] = "No bids"
            item['category'] = "N/A"
            item['image_url'] = "N/A"
            item['item_closing_time'] = "N/A"
        
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
            response = self.session.get(auction_url, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
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
            location = "N/A"
            phone = "N/A"
            location_elem = soup.find(string=re.compile(r'Location|Address', re.I))
            if location_elem:
                parent = location_elem.find_parent()
                if parent:
                    location_text = parent.get_text(strip=True)
                    # Remove "Location:" prefix
                    location_text = location_text.replace('Location:', '').replace('Auction', '').strip()
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
                'phone': 'N/A',
                'closing_date': 'N/A',
                'total_items': '0',
                'categories': 'N/A'
            }
    
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
        
        # Navigate through pages
        page_num = 1
        while True:
            if page_num == 1:
                page_url = auction_url
            else:
                page_url = f"{auction_url}?page={page_num}"
            
            logger.info(f"  Scraping page {page_num}: {page_url}")
            
            try:
                response = self.session.get(page_url, timeout=15)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Find all item containers
                # Strategy 1: Look for lot headings
                lot_containers = []
                lot_headings = soup.find_all(['h4', 'h5', 'h3'], string=re.compile(r'Lot:\s*\d+', re.I))
                
                for heading in lot_headings:
                    container = heading.find_parent(['div', 'article', 'section'])
                    if container:
                        lot_containers.append(container)
                
                # Strategy 2: Look for item links and get their parent containers
                if not lot_containers:
                    item_links = soup.find_all('a', href=re.compile(r'/item/\d+'))
                    seen = set()
                    for link in item_links:
                        parent = link.find_parent(['div', 'article', 'section'])
                        if parent and id(parent) not in seen:
                            seen.add(id(parent))
                            lot_containers.append(parent)
                
                if not lot_containers:
                    logger.info(f"  No items found on page {page_num}")
                    break
                
                logger.info(f"  Found {len(lot_containers)} potential item containers on page {page_num}")
                
                # Track seen items by URL to avoid duplicates
                seen_items = set()
                
                # Extract items
                for container in lot_containers:
                    try:
                        item = self.extract_item_from_container(container, auction_info)
                        if item and item.get('lot_number') != "N/A":
                            # Deduplicate by item URL
                            item_url = item.get('item_url', 'N/A')
                            if item_url != 'N/A' and item_url in seen_items:
                                logger.debug(f"    Skipping duplicate: {item_url}")
                                continue
                            
                            seen_items.add(item_url)
                            items.append(item)
                            self.stats['items_scraped'] += 1
                            logger.debug(f"    Extracted lot {item.get('lot_number')}: {item.get('item_title')[:50]}")
                            
                            # If a max_items limit exists, stop when reached
                            if max_items is not None and len(items) >= max_items:
                                logger.info(f"  Reached max_items limit: {max_items}")
                                return items
                    except Exception as e:
                        logger.warning(f"    Error extracting item: {e}")
                        self.stats['errors'] += 1
                
                # Check for next page
                next_link = soup.find('a', string=re.compile(r'Next\s*»', re.I))
                if not next_link:
                    logger.info(f"  No more pages for this auction")
                    break
                
                page_num += 1
                time.sleep(self.delay)
                
            except Exception as e:
                logger.error(f"  Error on page {page_num}: {e}")
                self.stats['errors'] += 1
                break
        
        logger.info(f"  Total items from auction: {len(items)}")
        return items
    
    def get_auction_list_pages(self):
        """Get all auction listing page URLs"""
        logger.info("Fetching auction list pages...")
        pages = []
        page_num = 1
        
        while True:
            url = f"{self.base_url}/auction/list?page={page_num}" if page_num > 1 else f"{self.base_url}/auction/list"
            
            try:
                response = self.session.get(url, timeout=15)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, 'html.parser')
                
                auction_links = soup.find_all('a', href=re.compile(r'/auction/\d+$'))
                
                if not auction_links:
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
        logger.info(f"Extracting auctions from: {page_url}")
        auctions = []
        
        try:
            response = self.session.get(page_url, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            auction_links = soup.find_all('a', href=re.compile(r'/auction/\d+$'))
            
            for link in auction_links:
                auction_url = urljoin(self.base_url, link['href'])
                if auction_url not in auctions:
                    auctions.append(auction_url)
            
            logger.info(f"  Found {len(auctions)} unique auctions")
            
        except Exception as e:
            logger.error(f"Error extracting auctions: {e}")
        
        return auctions
    
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
        for i, auction_url in enumerate(all_auction_urls, 1):
            logger.info(f"\n[{i}/{len(all_auction_urls)}] Scraping auction: {auction_url}")
            items = self.scrape_auction_items(auction_url)
            self.all_items.extend(items)
            time.sleep(self.delay)
        
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
        
        filename = os.path.join(self.run_dir, filename)
        logger.info(f"Saving {len(self.all_items)} items to {filename}...")
        
        # Column order: Logical flow from item details → money → time → links → metadata
        headers = [
            'lot_number', 'auction_title', 'item_title', 'short_description',
            'current_bid', 'next_required_bid', 'high_bidder',
            'item_closing_time', 'closing_date', 'item_url',
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