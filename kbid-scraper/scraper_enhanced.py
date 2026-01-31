"""
Production K-Bid Scraper
Uses verified selectors from actual K-Bid HTML source data
Clean, fast, accurate - no unnecessary overhead
"""

import logging
import time
import re
from typing import Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
import json

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup
import requests
from urllib.parse import urljoin

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class AuctionListing:
    """Auction listing data"""
    auction_id: str
    title: str
    url: str
    auctioneer: str
    location: str
    total_lots: int
    closing_date: Optional[str]
    status: str
    scraped_at: str


@dataclass
class ItemListing:
    """Complete item/lot data from K-Bid"""
    # Identifiers
    item_id: str
    lot_number: str
    auction_id: str
    
    # Basic info
    title: str
    description: str
    
    # Bidding information
    current_bid: Optional[float]
    next_required_bid: Optional[float]
    your_max_bid: Optional[float]
    high_bidder: Optional[str]
    bid_count: int
    
    # Status
    is_winning: bool
    reserve_met: bool
    
    # Media
    image_urls: List[str]
    primary_image_url: str
    
    # Timing
    closing_time: Optional[str]
    time_remaining: Optional[str]
    
    # Additional
    location: str
    item_url: str
    scraped_at: str


class ProductionKBidScraper:
    """
    Production K-Bid scraper using verified selectors from real source data
    """
    
    BASE_URL = "https://www.k-bid.com"
    
    # Verified selectors from actual K-Bid HTML
    SELECTORS = {
        # Primary selectors (highest reliability)
        'current_bid': '#lot_current_bid_lot_k-bid',  # Will use pattern matching
        'next_required_bid': '#lot_next_required_bid_lot_k-bid',  # Pattern matching
        'your_max_bid': '#lot_your_current_max_bid_lot_k-bid',  # Pattern matching
        'high_bidder': '#lot_current_high_bidder_detail_lot_k-bid',  # Pattern matching
        'winning_placeholder': '#winning_placeholder_lot_k-bid',  # Pattern matching
        
        # Content selectors
        'item_title': 'article.content-card > h3',
        'item_title_fallback': 'span.lot-title',
        'item_description': 'div.lot-description',
        
        # Image selectors
        'primary_image': 'div.galleria-image > img',
        'images_fallback': 'img.img-responsive',
        
        # Timing selectors
        'closing_time': 'span.lot-closing-time',
        'time_remaining': 'span.time-remaining',
        
        # Other info
        'bid_count': 'span.bid-count',
        'auction_title': 'h3#auction_title a',
    }
    
    def __init__(self, headless: bool = True, rate_limit: float = 1.5):
        """Initialize scraper with settings"""
        self.headless = headless
        self.rate_limit = rate_limit
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
    def _init_driver(self) -> Optional[webdriver.Chrome]:
        """Initialize Selenium WebDriver.

        If driver initialization fails (e.g. missing Chromedriver or low disk
        space prevents selenium-manager from provisioning binaries), return
        None so callers can fall back to a requests-only parsing mode.
        """
        options = webdriver.ChromeOptions()

        if self.headless:
            options.add_argument('--headless=new')

        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument('--disable-gpu')
        options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

        try:
            driver = webdriver.Chrome(options=options)
            # Try to mask automation flag
            try:
                driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            except Exception:
                # Non-fatal if the script execution fails
                pass
            return driver
        except Exception as e:
            logger.warning(
                "Selenium WebDriver initialization failed (%s). Falling back to requests-only parsing.",
                e
            )
            return None
    
    def _parse_currency(self, text: str) -> Optional[float]:
        """Parse currency string to float"""
        if not text:
            return None
        try:
            cleaned = re.sub(r'[$,\s]', '', text)
            return float(cleaned)
        except (ValueError, AttributeError):
            return None
    
    def _extract_ids_from_element_id(self, element_id: str) -> tuple:
        """Extract auction_id and lot_id from K-Bid element ID pattern"""
        if not element_id:
            return None, None
        match = re.search(r'lot_k-bid_(\d+)_(\d+)', element_id)
        if match:
            return match.group(1), match.group(2)
        return None, None
    
    def _find_element_by_id_pattern(self, soup, pattern: str):
        """Find element by ID pattern (e.g., 'lot_current_bid_lot_k-bid')"""
        elements = soup.find_all(id=re.compile(f'{pattern}_\\d+_\\d+'))
        return elements[0] if elements else None
    
    def _get_text_safe(self, element) -> str:
        """Safely get text from element"""
        if element:
            return element.get_text(strip=True)
        return ""
    
    def scrape_auction_list(self, status: str = "active") -> List[AuctionListing]:
        """Scrape all auctions using the same requests-based pagination workflow
        as the original `kbid_scraper.KBidScraper`.

        This method prefers the requests + BeautifulSoup workflow to discover
        auction listing pages and extract auction URLs. It returns a list of
        AuctionListing dataclass instances populated with basic metadata.
        """
        logger.info(f"Scraping auction list (status={status})...")

        # Discover listing pages (pagination)
        try:
            pages = self.get_auction_list_pages()
        except Exception as e:
            logger.error(f"Failed to discover auction listing pages: {e}")
            return []

        auctions: List[AuctionListing] = []

        for page_url in pages:
            try:
                found = self.get_auctions_from_page(page_url)
                for info in found:
                    auction_url = info.get('url')
                    auction_id = auction_url.rstrip('/').split('/')[-1]
                    title = info.get('title') or ''
                    auctions.append(AuctionListing(
                        auction_id=auction_id,
                        title=title,
                        url=auction_url,
                        auctioneer="Unknown",
                        location="Unknown",
                        total_lots=0,
                        closing_date=None,
                        status="Unknown",
                        scraped_at=datetime.now().isoformat()
                    ))
            except Exception as e:
                logger.warning(f"Error extracting auctions from page {page_url}: {e}")

        logger.info(f"Discovered {len(auctions)} auctions from {len(pages)} listing pages")
        return auctions

    def get_auction_list_pages(self) -> List[str]:
        """Return paginated auction list page URLs by following listing pagination.

        Mirrors the approach used in the legacy scraper: request each
        /auction/list?page=N page until no auctions are found or pagination ends.
        """
        pages = []
        page_num = 1

        while True:
            url = f"{self.BASE_URL}/auction/list?page={page_num}" if page_num > 1 else f"{self.BASE_URL}/auction/list"
            try:
                resp = self.session.get(url, timeout=15)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.content, 'html.parser')

                auction_links = soup.find_all('a', href=re.compile(r'/auction/\d+$'))
                if not auction_links:
                    logger.info(f"No auctions found on listing page {page_num}, stopping pagination")
                    break

                pages.append(url)

                # Check for a 'Next' link to continue pagination
                next_link = soup.find('a', string=re.compile(r'Next\s*»'))
                if not next_link:
                    break

                page_num += 1
                time.sleep(self.rate_limit)
            except requests.RequestException as e:
                logger.error(f"HTTP error fetching listing page {page_num}: {e}")
                break

        return pages

    def get_auctions_from_page(self, page_url: str) -> List[Dict[str, str]]:
        """Extract auction URLs and titles from a listing page URL.

        Returns a list of dicts with keys: 'url' and 'title'.
        """
        try:
            resp = self.session.get(page_url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, 'html.parser')

            auction_links = soup.find_all('a', href=re.compile(r'/auction/\d+$'))
            results = []
            seen = set()
            for a in auction_links:
                href = a.get('href')
                if not href:
                    continue
                if href in seen:
                    continue
                seen.add(href)
                full = urljoin(self.BASE_URL, href)
                title = a.get_text(strip=True) or full
                results.append({'url': full, 'title': title})

            time.sleep(self.rate_limit)
            return results
        except requests.RequestException as e:
            logger.error(f"Error fetching auctions from {page_url}: {e}")
            return []
    
    def _parse_auction_container(self, container) -> Optional[AuctionListing]:
        """Parse auction container"""
        try:
            # Title and link
            title_elem = container.find('h4')
            if not title_elem:
                return None
            
            link_elem = title_elem.find('a', href=True)
            if not link_elem:
                return None
            
            auction_url = urljoin(self.BASE_URL, link_elem['href'])
            auction_id = auction_url.rstrip('/').split('/')[-1]
            title = self._get_text_safe(link_elem)
            
            # Auctioneer
            auctioneer_elem = container.find('strong')
            auctioneer = self._get_text_safe(auctioneer_elem) or "Unknown"
            
            # Location
            text_content = container.get_text()
            location = "Unknown"
            state_match = re.search(r'([A-Z]{2})\s+\d{5}', text_content)
            if state_match:
                lines = [line.strip() for line in text_content.split('\n') if line.strip()]
                for line in lines:
                    if state_match.group(1) in line:
                        location = line
                        break
            
            # Lot count
            total_lots = 0
            lots_match = re.search(r'(\d+)\s+Lots?\s+Open', text_content, re.IGNORECASE)
            if lots_match:
                total_lots = int(lots_match.group(1))
            
            # Closing date
            closing_date = None
            closing_match = re.search(r'(Begins Closing|Closing)\s+([^\n]+)', text_content)
            if closing_match:
                closing_date = closing_match.group(2).strip()
            
            # Status
            status = "Active"
            if "Closed" in text_content or "Ended" in text_content:
                status = "Closed"
            elif "Upcoming" in text_content:
                status = "Upcoming"
            
            return AuctionListing(
                auction_id=auction_id,
                title=title,
                url=auction_url,
                auctioneer=auctioneer,
                location=location,
                total_lots=total_lots,
                closing_date=closing_date,
                status=status,
                scraped_at=datetime.now().isoformat()
            )
            
        except Exception as e:
            logger.error(f"Error parsing auction: {e}")
            return None
    
    def scrape_auction_items(self, auction_id: str, max_items: Optional[int] = None) -> List[ItemListing]:
        """Scrape all items from a specific auction"""
        logger.info(f"Scraping items for auction {auction_id}...")
        url = f"{self.BASE_URL}/auction/{auction_id}"
        
        driver = self._init_driver()
        items = []

        try:
            if driver:
                driver.get(url)
                try:
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.TAG_NAME, "body"))
                    )
                except Exception:
                    pass
                time.sleep(2)

                # Scroll to load all items
                try:
                    last_height = driver.execute_script("return document.body.scrollHeight")
                    for _ in range(10):
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(1.5)
                        new_height = driver.execute_script("return document.body.scrollHeight")
                        if new_height == last_height:
                            break
                        last_height = new_height
                except Exception:
                    # If scrolling isn't supported in this environment, continue
                    pass

                soup = BeautifulSoup(driver.page_source, 'html.parser')
            else:
                # Requests-only fallback
                resp = self.session.get(url, timeout=15)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.content, 'html.parser')
            
            # Find lot containers
            containers = self._find_lot_containers(soup)
            logger.info(f"Found {len(containers)} items")
            
            for idx, container in enumerate(containers):
                if max_items and idx >= max_items:
                    break

                item = self._parse_item_container(container, auction_id)
                if not item:
                    continue

                # If we couldn't extract a current_bid from the listing container,
                # try fetching the item detail page (requests-only path) to populate missing fields.
                if (item.current_bid is None or item.current_bid == 0) and item.item_url:
                    try:
                        details = self.scrape_item_details(item.item_url)
                        if details:
                            # update fields conservatively
                            if details.get('current_bid') is not None:
                                item.current_bid = details.get('current_bid')
                            if details.get('next_required_bid') is not None:
                                item.next_required_bid = details.get('next_required_bid')
                            if details.get('high_bidder') is not None:
                                item.high_bidder = details.get('high_bidder')
                            if details.get('images'):
                                item.image_urls = details.get('images')
                                item.primary_image_url = details.get('images')[0] if details.get('images') else item.primary_image_url
                            if details.get('description'):
                                item.description = details.get('description')
                    except Exception as e:
                        logger.debug(f"Detail fetch failed for {item.item_url}: {e}")

                items.append(item)
            
            logger.info(f"Scraped {len(items)} items")
            
        except Exception as e:
            logger.error(f"Error scraping items: {e}")
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
        
        return items
    
    def _find_lot_containers(self, soup) -> List:
        """Find all item containers on page"""
        # Strategy 1: content cards (common template)
        containers = soup.find_all('article', class_='content-card')

        # Strategy 2: grid columns used in some layouts
        if not containers:
            containers = soup.find_all('div', class_=['col-md-4', 'col-sm-6'])

        # Strategy 3: legacy scraper - look for headings with 'Lot: N'
        if not containers:
            lot_headings = []
            for tag in ['h4', 'h5', 'h3', 'h6']:
                found = soup.find_all(tag, string=re.compile(r'Lot:\s*\d+', re.I))
                lot_headings.extend(found)

            if lot_headings:
                containers = []
                for h in lot_headings:
                    parent = h.find_parent(['div', 'article', 'section'])
                    if parent and parent not in containers:
                        containers.append(parent)

        # Strategy 4: find /auction/ID/item/ID links and use their parent container
        if not containers:
            lot_links = soup.find_all('a', href=re.compile(r'/auction/\d+/item/\d+'))
            seen_containers = set()
            containers = []
            for link in lot_links:
                parent = link.find_parent(['div', 'article', 'section'])
                if parent and id(parent) not in seen_containers:
                    seen_containers.add(id(parent))
                    containers.append(parent)

        # Strategy 5: fallback - find containers that include 'Current Bid' and an image or item link
        if not containers:
            candidates = soup.find_all(['div', 'article', 'section'])
            for container in candidates:
                try:
                    if (container.find(string=re.compile(r'Current Bid|Lot:', re.I)) and 
                        (container.find('img') or container.find('a', href=re.compile(r'/item/')))):
                        containers.append(container)
                except Exception:
                    continue

        # Filter containers to likely item containers to avoid pagination/ads
        def is_likely_item(c):
            try:
                # Must have an item link or title or bid or an image
                # Exclude common page chrome / user links
                hrefs = [a.get('href','') for a in c.find_all('a', href=True)]
                for h in hrefs:
                    if h and h.startswith('/user'):
                        return False

                if c.find('a', href=re.compile(r'/item/')):
                    return True
                if c.find(class_=re.compile(r'lot-title|content-card|content-card__title')):
                    return True
                if c.select_one('.lot-current-bid'):
                    return True
                txt = c.get_text('\n', strip=True)
                # Avoid matching site chrome like 'Showing 1 to 50', 'Prev', 'Next', 'Register'
                if re.search(r'Lot:\s*\d+', txt, re.I):
                    return True
                return False
            except Exception:
                return False

        filtered = [c for c in containers if is_likely_item(c)]
        # If filtering removed everything, fall back to the original containers
        if not filtered and containers:
            return containers
        return filtered
    
    def _parse_item_container(self, container, auction_id: str) -> Optional[ItemListing]:
        """Parse item container using verified selectors"""
        try:
            # Accept either a container element or a heading/link node; mirror legacy behavior
            lot_elem = container
            if getattr(lot_elem, 'name', None) in ('a', 'h4', 'h5', 'h3', 'h2', 'h6'):
                # find a suitable parent container
                parent = lot_elem.find_parent(['div', 'article', 'section'])
                if parent:
                    container = parent
                else:
                    # fallback to the direct parent
                    container = lot_elem.parent or lot_elem
            logger.debug("Parsing item container")
            # Title (required) - try selectors first, then fall back to heading/link heuristics
            title_elem = None
            title_elem = container.select_one(self.SELECTORS.get('item_title')) if container else None
            if not title_elem:
                title_elem = container.select_one(self.SELECTORS.get('item_title_fallback')) if container else None

            # Fallback: look for heading tags or item link text similar to legacy scraper
            if not title_elem:
                for tag in ['h2', 'h3', 'h4', 'h5']:
                    t = container.find(tag)
                    if t and t.get_text(strip=True):
                        title_elem = t
                        break
            if not title_elem:
                # look for a link to the item
                link_candidate = container.find('a', href=re.compile(r'/item/'))
                if link_candidate and link_candidate.get_text(strip=True) and 'Click for Details' not in link_candidate.get_text(strip=True):
                    title_elem = link_candidate

            if not title_elem:
                # Last-resort: try to infer a title from container text (legacy scraper used similar heuristics)
                full_text = container.get_text(separator='\n', strip=True)
                lines = [ln.strip() for ln in full_text.split('\n') if ln.strip()]
                inferred = None
                for ln in lines:
                    # prefer short lines that look like a title (not 'Lot:' or 'Current Bid')
                    if len(ln) > 3 and not re.search(r'Lot:|Current Bid|Next Required', ln, re.I):
                        inferred = ln
                        break
                if inferred:
                    logger.info("Using inferred title for container: %s", inferred[:120])
                    title = inferred
                else:
                    logger.warning("No title element found for container; skipping. snippet=%s", str(container)[:200])
                    return None
            else:
                title = self._get_text_safe(title_elem)
            
            # Extract IDs and attempt to get current bid from container
            auction_id_extracted = auction_id
            lot_id = None
            current_bid = None

            # Try class-based selector first (more general)
            bid_elem = container.select_one('.lot-current-bid') if container else None
            if not bid_elem:
                # Next try id-pattern elements used by template
                bid_elem = self._find_element_by_id_pattern(container, 'lot_current_bid_lot_k-bid')

            if bid_elem:
                current_bid = self._parse_currency(self._get_text_safe(bid_elem))
                element_id = bid_elem.get('id', '')
                a_id, l_id = self._extract_ids_from_element_id(element_id)
                if a_id:
                    auction_id_extracted = a_id
                if l_id:
                    lot_id = l_id
            
            if not lot_id:
                lot_id = f"lot_{abs(hash(title)) % 1000000}"

            logger.debug("Parsed base item: title=%s lot_id=%s", title, lot_id)
            
            # Next required bid
            next_required_bid = None
            next_bid_elem = container.select_one('.lot-next-required-bid') if container else None
            if not next_bid_elem:
                next_bid_elem = self._find_element_by_id_pattern(container, 'lot_next_required_bid_lot_k-bid')
            if next_bid_elem:
                next_required_bid = self._parse_currency(self._get_text_safe(next_bid_elem))
            
            # Your max bid
            your_max_bid = None
            max_bid_elem = self._find_element_by_id_pattern(container, 'lot_your_current_max_bid_lot_k-bid')
            if max_bid_elem:
                your_max_bid = self._parse_currency(self._get_text_safe(max_bid_elem))
            
            # High bidder
            high_bidder = None
            bidder_elem = self._find_element_by_id_pattern(container, 'lot_current_high_bidder_detail_lot_k-bid')
            if bidder_elem:
                high_bidder = self._get_text_safe(bidder_elem)
            
            # Winning status
            is_winning = False
            placeholder_elem = self._find_element_by_id_pattern(container, 'winning_placeholder_lot_k-bid')
            if placeholder_elem:
                classes = ' '.join(placeholder_elem.get('class', []))
                is_winning = 'winning' in classes.lower()
            
            # Description
            desc_elem = container.select_one(self.SELECTORS['item_description'])
            description = self._get_text_safe(desc_elem)
            
            # Images
            image_urls = []
            primary_image_url = ""
            img_elem = container.select_one(self.SELECTORS['primary_image'])
            if not img_elem:
                img_elem = container.select_one(self.SELECTORS['images_fallback'])
            if img_elem:
                primary_image_url = img_elem.get('src', '')
                image_urls.append(primary_image_url)
            
            # Closing time
            closing_elem = container.select_one(self.SELECTORS['closing_time'])
            closing_time = self._get_text_safe(closing_elem)
            
            # Time remaining
            time_elem = container.select_one(self.SELECTORS['time_remaining'])
            time_remaining = self._get_text_safe(time_elem)
            
            # Bid count
            bid_count = 0
            bid_count_elem = container.select_one(self.SELECTORS['bid_count'])
            if bid_count_elem:
                bid_text = self._get_text_safe(bid_count_elem)
                match = re.search(r'(\d+)', bid_text)
                if match:
                    bid_count = int(match.group(1))
            
            # Item URL: prefer explicit /item/ link; do NOT accept arbitrary anchors (nav/login)
            item_url = ""
            item_link = container.find('a', href=re.compile(r'/item/'))
            if not item_link:
                # also accept anchors that are explicitly marked as lot-title links
                item_link = container.find('a', class_=re.compile(r'lot-title|lot-link'))

            if item_link and item_link.get('href'):
                href = item_link['href']
                # ignore user/account or pagination anchors
                if href.startswith('/user') or href.startswith('#'):
                    item_link = None
                else:
                    item_url = urljoin(self.BASE_URL, href)
                # Extract item_id from URL
                url_parts = item_url.rstrip('/').split('/')
                if 'item' in url_parts:
                    item_idx = url_parts.index('item')
                    if item_idx + 1 < len(url_parts):
                        item_id = url_parts[item_idx + 1]
                    else:
                        item_id = lot_id
                else:
                    item_id = lot_id
            else:
                item_id = lot_id
            
            # Reserve met
            reserve_met = 'reserve-met' in str(container).lower() or 'reserve met' in str(container).lower()
            
            return ItemListing(
                item_id=item_id,
                lot_number=lot_id,
                auction_id=auction_id_extracted or auction_id,
                title=title,
                description=description,
                current_bid=current_bid,
                next_required_bid=next_required_bid,
                your_max_bid=your_max_bid,
                high_bidder=high_bidder,
                bid_count=bid_count,
                is_winning=is_winning,
                reserve_met=reserve_met,
                image_urls=image_urls,
                primary_image_url=primary_image_url,
                closing_time=closing_time,
                time_remaining=time_remaining,
                location="",
                item_url=item_url,
                scraped_at=datetime.now().isoformat()
            )
            
        except Exception as e:
            logger.exception("Error parsing item: %s", e)
            return None
    
    def scrape_item_details(self, item_url: str) -> Optional[Dict]:
        """Scrape full details for a specific item"""
        logger.info(f"Scraping item: {item_url}")
        driver = self._init_driver()

        try:
            if driver:
                driver.get(item_url)
                try:
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.TAG_NAME, "body"))
                    )
                except Exception:
                    pass
                time.sleep(self.rate_limit)
                soup = BeautifulSoup(driver.page_source, 'html.parser')
            else:
                resp = self.session.get(item_url, timeout=15)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.content, 'html.parser')
            
            details = {'url': item_url, 'scraped_at': datetime.now().isoformat()}
            
            # Title
            title_elem = soup.select_one(self.SELECTORS['item_title'])
            if not title_elem:
                title_elem = soup.select_one(self.SELECTORS['item_title_fallback'])
            details['title'] = self._get_text_safe(title_elem)
            
            # Current bid and IDs
            bid_elem = self._find_element_by_id_pattern(soup, 'lot_current_bid_lot_k-bid')
            if bid_elem:
                details['current_bid'] = self._parse_currency(self._get_text_safe(bid_elem))
                element_id = bid_elem.get('id', '')
                auction_id, lot_id = self._extract_ids_from_element_id(element_id)
                details['auction_id'] = auction_id
                details['lot_id'] = lot_id
            
            # Next required bid
            next_bid_elem = self._find_element_by_id_pattern(soup, 'lot_next_required_bid_lot_k-bid')
            if next_bid_elem:
                details['next_required_bid'] = self._parse_currency(self._get_text_safe(next_bid_elem))
            
            # Your max bid
            max_bid_elem = self._find_element_by_id_pattern(soup, 'lot_your_current_max_bid_lot_k-bid')
            if max_bid_elem:
                details['your_max_bid'] = self._parse_currency(self._get_text_safe(max_bid_elem))
            
            # High bidder
            bidder_elem = self._find_element_by_id_pattern(soup, 'lot_current_high_bidder_detail_lot_k-bid')
            if bidder_elem:
                details['high_bidder'] = self._get_text_safe(bidder_elem)
            
            # Winning status
            placeholder_elem = self._find_element_by_id_pattern(soup, 'winning_placeholder_lot_k-bid')
            if placeholder_elem:
                classes = ' '.join(placeholder_elem.get('class', []))
                details['is_winning'] = 'winning' in classes.lower()
            
            # Description
            desc_elem = soup.select_one(self.SELECTORS['item_description'])
            details['description'] = self._get_text_safe(desc_elem)
            
            # Images
            img_elems = soup.select(self.SELECTORS['primary_image'])
            details['images'] = [img.get('src', '') for img in img_elems if img.get('src')]
            
            # Closing time
            closing_elem = soup.select_one(self.SELECTORS['closing_time'])
            details['closing_time'] = self._get_text_safe(closing_elem)
            
            # Time remaining
            time_elem = soup.select_one(self.SELECTORS['time_remaining'])
            details['time_remaining'] = self._get_text_safe(time_elem)
            
            # Bid count
            bid_count_elem = soup.select_one(self.SELECTORS['bid_count'])
            if bid_count_elem:
                bid_text = self._get_text_safe(bid_count_elem)
                match = re.search(r'(\d+)', bid_text)
                details['bid_count'] = int(match.group(1)) if match else 0
            
            # Auction title
            auction_title_elem = soup.select_one(self.SELECTORS['auction_title'])
            if auction_title_elem:
                details['auction_title'] = self._get_text_safe(auction_title_elem)
                details['auction_url'] = urljoin(self.BASE_URL, auction_title_elem.get('href', ''))
            
            return details
            
        except Exception as e:
            logger.error(f"Error scraping item details: {e}")
            return None
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
    
    def export_to_json(self, data: List, filename: str):
        """Export data to JSON"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(
                    [asdict(item) if hasattr(item, '__dataclass_fields__') else item for item in data],
                    f,
                    indent=2,
                    ensure_ascii=False,
                    default=str
                )
            logger.info(f"Exported to {filename}")
        except Exception as e:
            logger.error(f"Export error: {e}")


def main():
    """Example usage"""
    scraper = ProductionKBidScraper(headless=True, rate_limit=1.5)
    
    # Scrape auctions
    print("Scraping auctions...")
    auctions = scraper.scrape_auction_list()
    print(f"Found {len(auctions)} auctions")
    
    if auctions:
        # Scrape first auction
        print(f"\nScraping items from auction {auctions[0].auction_id}...")
        items = scraper.scrape_auction_items(auctions[0].auction_id, max_items=5)
        print(f"Found {len(items)} items")
        
        if items:
            # Show first item
            item = items[0]
            print(f"\nSample Item:")
            print(f"  Title: {item.title}")
            print(f"  Current Bid: ${item.current_bid}" if item.current_bid else "  No bids yet")
            print(f"  Next Required: ${item.next_required_bid}" if item.next_required_bid else "")
            print(f"  High Bidder: {item.high_bidder}" if item.high_bidder else "")
            print(f"  Winning: {item.is_winning}")
            print(f"  Bid Count: {item.bid_count}")
            print(f"  URL: {item.item_url}")
            
            # Export
            scraper.export_to_json(items, 'items.json')


if __name__ == '__main__':
    main()