# API Integration Guide for Auction Market Analysis

## Overview

This guide provides specific, production-ready examples for integrating with major marketplace APIs to gather real-time pricing data.

---

## 1. eBay Finding API Integration

### Why eBay Sold Listings Are Gold

eBay sold listings represent **actual transaction prices**, not asking prices. This is the most reliable market data available.

### Setup

```bash
# Register for eBay Developer Account
# https://developer.ebay.com/signin

# Get API credentials (free tier available)
# - App ID (Client ID)
# - Cert ID (Client Secret)
```

### Finding API - Sold Listings Search

```python
import requests
from datetime import datetime, timedelta

class EBayResearcher:
    def __init__(self, app_id: str):
        self.app_id = app_id
        self.base_url = "https://svcs.ebay.com/services/search/FindingService/v1"
    
    def find_sold_items(self, keywords: str, condition: str = None, max_results: int = 100):
        """
        Search eBay sold/completed listings
        
        Args:
            keywords: Product search query
            condition: "New", "Used", "For parts or not working"
            max_results: Max items to return (100 max per call)
        """
        
        # Build item filters
        filters = [
            {
                "name": "SoldItemsOnly",
                "value": "true"
            },
            {
                "name": "EndTimeFrom",
                "value": (datetime.now() - timedelta(days=90)).isoformat() + "Z"
            }
        ]
        
        if condition:
            condition_map = {
                "New": "1000",
                "Like New": "1500", 
                "Excellent": "2000",
                "Good": "3000",
                "Fair": "4000",
                "Poor": "5000",
                "Parts": "7000"
            }
            filters.append({
                "name": "Condition",
                "value": condition_map.get(condition, "3000")
            })
        
        # Build request parameters
        params = {
            "OPERATION-NAME": "findCompletedItems",
            "SERVICE-VERSION": "1.0.0",
            "SECURITY-APPNAME": self.app_id,
            "RESPONSE-DATA-FORMAT": "JSON",
            "REST-PAYLOAD": "",
            "keywords": keywords,
            "paginationInput.entriesPerPage": str(max_results),
            "sortOrder": "EndTimeSoonest"
        }
        
        # Add item filters
        for i, filter_item in enumerate(filters):
            params[f"itemFilter({i}).name"] = filter_item["name"]
            params[f"itemFilter({i}).value"] = filter_item["value"]
        
        try:
            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            return self._parse_sold_items(data)
            
        except requests.exceptions.RequestException as e:
            print(f"eBay API error: {e}")
            return []
    
    def _parse_sold_items(self, response_data):
        """Extract sold prices from eBay response"""
        
        items = []
        
        try:
            search_result = response_data.get("findCompletedItemsResponse", [{}])[0]
            search_results = search_result.get("searchResult", [{}])[0]
            
            if search_results.get("@count") == "0":
                return items
            
            item_list = search_results.get("item", [])
            
            for item in item_list:
                # Only include items that actually sold
                selling_status = item.get("sellingStatus", [{}])[0]
                selling_state = selling_status.get("sellingState", [""])[0]
                
                if selling_state != "EndedWithSales":
                    continue
                
                # Extract price
                price_info = selling_status.get("convertedCurrentPrice", [{}])[0]
                price = float(price_info.get("__value__", 0))
                
                # Extract other useful data
                title = item.get("title", [""])[0]
                item_id = item.get("itemId", [""])[0]
                end_time = item.get("listingInfo", [{}])[0].get("endTime", [""])[0]
                condition = item.get("condition", [{}])[0].get("conditionDisplayName", [""])[0]
                shipping = item.get("shippingInfo", [{}])[0].get("shippingServiceCost", [{}])[0].get("__value__", "0")
                
                items.append({
                    "price": price,
                    "title": title,
                    "item_id": item_id,
                    "end_time": end_time,
                    "condition": condition,
                    "shipping_cost": float(shipping)
                })
        
        except (KeyError, IndexError, ValueError) as e:
            print(f"Error parsing eBay response: {e}")
        
        return items


# Usage example
researcher = EBayResearcher(app_id="YOUR_EBAY_APP_ID")
sold_items = researcher.find_sold_items(
    keywords="Vissani 7.2 refrigerator",
    condition="Fair",
    max_results=50
)

# Calculate statistics
prices = [item["price"] for item in sold_items]
if prices:
    import numpy as np
    median_price = np.median(prices)
    print(f"Found {len(prices)} sold items, median price: ${median_price:.2f}")
```

### Advanced: Multiple Page Results

```python
def get_all_sold_items(self, keywords: str, condition: str = None, max_pages: int = 5):
    """Fetch multiple pages of results"""
    
    all_items = []
    
    for page in range(1, max_pages + 1):
        params = {
            "OPERATION-NAME": "findCompletedItems",
            "SERVICE-VERSION": "1.0.0",
            "SECURITY-APPNAME": self.app_id,
            "RESPONSE-DATA-FORMAT": "JSON",
            "keywords": keywords,
            "paginationInput.entriesPerPage": "100",
            "paginationInput.pageNumber": str(page),
            # ... other params
        }
        
        response = requests.get(self.base_url, params=params)
        items = self._parse_sold_items(response.json())
        
        if not items:
            break  # No more results
        
        all_items.extend(items)
        
        # Rate limiting - eBay allows 5000 calls/day
        import time
        time.sleep(0.2)  # Be nice to the API
    
    return all_items
```

---

## 2. Amazon Product Advertising API (PA-API 5.0)

### Setup

```bash
# Sign up for Amazon Associates program
# https://affiliate-program.amazon.com/

# Request PA-API access
# https://webservices.amazon.com/paapi5/documentation/

# Get credentials:
# - Access Key
# - Secret Key
# - Associate Tag (Partner Tag)
```

### Implementation Using python-amazon-paapi

```python
from amazon.paapi import AmazonAPI

class AmazonResearcher:
    def __init__(self, access_key: str, secret_key: str, partner_tag: str):
        self.api = AmazonAPI(
            access_key=access_key,
            secret_key=secret_key,
            partner_tag=partner_tag,
            country="US"
        )
    
    def search_products(self, keywords: str, max_results: int = 10):
        """Search Amazon for products"""
        
        try:
            # Search for items
            items = self.api.search_items(
                keywords=keywords,
                item_count=max_results,
                resources=[
                    "ItemInfo.Title",
                    "Offers.Listings.Price",
                    "Offers.Listings.Condition",
                    "Images.Primary.Large"
                ]
            )
            
            products = []
            
            for item in items.items:
                # Get price information
                if item.offers and item.offers.listings:
                    listing = item.offers.listings[0]
                    
                    if listing.price and listing.price.amount:
                        price = listing.price.amount
                        
                        products.append({
                            "asin": item.asin,
                            "title": item.item_info.title.display_value if item.item_info.title else "",
                            "price": price,
                            "condition": listing.condition.value if listing.condition else "New",
                            "currency": listing.price.currency if listing.price else "USD"
                        })
            
            return products
            
        except Exception as e:
            print(f"Amazon API error: {e}")
            return []
    
    def get_item_details(self, asin: str):
        """Get detailed info for specific ASIN"""
        
        try:
            item = self.api.get_items(
                item_ids=[asin],
                resources=[
                    "ItemInfo.Title",
                    "ItemInfo.Features",
                    "ItemInfo.TechnicalInfo",
                    "Offers.Listings.Price",
                    "BrowseNodeInfo.BrowseNodes"
                ]
            )[0]
            
            # Extract detailed information
            details = {
                "asin": asin,
                "title": item.item_info.title.display_value if item.item_info.title else "",
                "features": [],
                "price": None
            }
            
            # Get features
            if item.item_info.features:
                details["features"] = [f.display_value for f in item.item_info.features.display_values]
            
            # Get price
            if item.offers and item.offers.listings:
                listing = item.offers.listings[0]
                if listing.price:
                    details["price"] = listing.price.amount
            
            return details
            
        except Exception as e:
            print(f"Error fetching ASIN {asin}: {e}")
            return None


# Usage
amazon = AmazonResearcher(
    access_key="YOUR_ACCESS_KEY",
    secret_key="YOUR_SECRET_KEY",
    partner_tag="YOUR_PARTNER_TAG"
)

results = amazon.search_products("Vissani refrigerator")
for product in results:
    print(f"{product['title']}: ${product['price']}")
```

---

## 3. Keepa API (Amazon Price History)

Keepa tracks Amazon price history, which is incredibly valuable for understanding price trends.

```python
import requests

class KeepaResearcher:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.keepa.com"
    
    def get_price_history(self, asin: str, domain: int = 1):
        """
        Get historical price data for an Amazon product
        
        Args:
            asin: Amazon ASIN
            domain: 1=US, 2=UK, 3=DE, etc.
        """
        
        url = f"{self.base_url}/product"
        params = {
            "key": self.api_key,
            "domain": domain,
            "asin": asin,
            "stats": 90  # Stats for last 90 days
        }
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data.get("products"):
                product = data["products"][0]
                
                # Parse price history
                # Keepa uses a special time format (minutes since epoch 2000-01-01)
                csv_data = product.get("csv", [])
                
                # Extract Amazon price history (index 0 is Amazon price)
                if len(csv_data) > 0:
                    amazon_prices = self._parse_keepa_prices(csv_data[0])
                    
                    return {
                        "asin": asin,
                        "current_price": amazon_prices[-1]["price"] if amazon_prices else None,
                        "avg_90day": product.get("stats", {}).get("avg", [None]*31)[0],
                        "min_90day": product.get("stats", {}).get("min", [None]*31)[0],
                        "max_90day": product.get("stats", {}).get("max", [None]*31)[0],
                        "price_history": amazon_prices
                    }
            
            return None
            
        except Exception as e:
            print(f"Keepa API error: {e}")
            return None
    
    def _parse_keepa_prices(self, csv_array):
        """Parse Keepa's CSV format"""
        prices = []
        
        # CSV format: [time1, price1, time2, price2, ...]
        for i in range(0, len(csv_array), 2):
            if i + 1 < len(csv_array):
                time_minutes = csv_array[i]
                price_cents = csv_array[i + 1]
                
                if price_cents != -1:  # -1 means no data
                    # Convert Keepa time to datetime
                    # Keepa epoch: 2011-01-01 00:00:00
                    from datetime import datetime, timedelta
                    keepa_epoch = datetime(2011, 1, 1)
                    timestamp = keepa_epoch + timedelta(minutes=time_minutes)
                    
                    prices.append({
                        "timestamp": timestamp.isoformat(),
                        "price": price_cents / 100  # Convert cents to dollars
                    })
        
        return prices


# Usage
keepa = KeepaResearcher(api_key="YOUR_KEEPA_API_KEY")
history = keepa.get_price_history(asin="B08N5WRWNW")

if history:
    print(f"Current: ${history['current_price']:.2f}")
    print(f"90-day avg: ${history['avg_90day']:.2f}")
    print(f"90-day range: ${history['min_90day']:.2f} - ${history['max_90day']:.2f}")
```

---

## 4. Web Scraping (Facebook Marketplace, Mercari, etc.)

For platforms without APIs, use ethical web scraping.

### Facebook Marketplace Scraper

```python
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time

class FacebookMarketplaceScraper:
    def __init__(self):
        # Use headless Chrome
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--disable-blink-features=AutomationControlled')
        self.driver = webdriver.Chrome(options=options)
    
    def search_items(self, query: str, location: str = "Minneapolis, MN"):
        """Search Facebook Marketplace"""
        
        # Build search URL
        encoded_query = query.replace(" ", "%20")
        url = f"https://www.facebook.com/marketplace/minneapolis/search/?query={encoded_query}"
        
        try:
            self.driver.get(url)
            
            # Wait for results to load
            time.sleep(3)
            
            # Scroll to load more items
            for _ in range(3):
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
            
            # Parse page
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            # Find listing elements (selectors may change - inspect page)
            listings = soup.find_all('div', {'data-testid': lambda x: x and 'marketplace-listing' in str(x)})
            
            items = []
            
            for listing in listings:
                try:
                    # Extract price
                    price_elem = listing.find('span', string=lambda x: x and '$' in str(x))
                    if price_elem:
                        price_text = price_elem.text.strip().replace('$', '').replace(',', '')
                        price = float(price_text)
                        
                        # Extract title
                        title_elem = listing.find('span', {'class': lambda x: x and 'title' in str(x).lower()})
                        title = title_elem.text if title_elem else ""
                        
                        items.append({
                            "title": title,
                            "price": price,
                            "platform": "Facebook Marketplace"
                        })
                
                except Exception as e:
                    continue
            
            return items
            
        except Exception as e:
            print(f"Facebook scraping error: {e}")
            return []
        
        finally:
            self.driver.quit()


# Usage (use sparingly and ethically)
scraper = FacebookMarketplaceScraper()
results = scraper.search_items("Vissani refrigerator")
```

---

## 5. Google Shopping API

```python
import requests

class GoogleShoppingResearcher:
    def __init__(self, api_key: str, cx: str):
        """
        Args:
            api_key: Google Custom Search API key
            cx: Custom Search Engine ID
        """
        self.api_key = api_key
        self.cx = cx
        self.base_url = "https://www.googleapis.com/customsearch/v1"
    
    def search_products(self, query: str):
        """Search Google Shopping"""
        
        params = {
            "key": self.api_key,
            "cx": self.cx,
            "q": query,
            "searchType": "image",  # Can help find shopping results
            "num": 10
        }
        
        try:
            response = requests.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()
            
            items = []
            
            for item in data.get("items", []):
                # Extract product info from snippets
                title = item.get("title", "")
                link = item.get("link", "")
                snippet = item.get("snippet", "")
                
                # Try to extract price from snippet
                import re
                price_match = re.search(r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)', snippet)
                
                if price_match:
                    price = float(price_match.group(1).replace(',', ''))
                    
                    items.append({
                        "title": title,
                        "price": price,
                        "url": link,
                        "platform": "Google Shopping"
                    })
            
            return items
            
        except Exception as e:
            print(f"Google Shopping error: {e}")
            return []
```

---

## 6. Combining All Sources

```python
import asyncio
import aiohttp

class MultiSourcePriceResearcher:
    """Combine data from all sources"""
    
    def __init__(self, 
                 ebay_app_id: str,
                 amazon_keys: dict,
                 keepa_key: str = None):
        self.ebay = EBayResearcher(ebay_app_id)
        self.amazon = AmazonResearcher(**amazon_keys)
        self.keepa = KeepaResearcher(keepa_key) if keepa_key else None
    
    async def research_comprehensive(self, product_query: str, condition: str = "Good"):
        """Get prices from all sources in parallel"""
        
        # Create tasks for parallel execution
        tasks = []
        
        # eBay sold listings (most important)
        ebay_task = asyncio.create_task(
            asyncio.to_thread(
                self.ebay.find_sold_items,
                keywords=product_query,
                condition=condition
            )
        )
        tasks.append(("ebay", ebay_task))
        
        # Amazon current prices
        amazon_task = asyncio.create_task(
            asyncio.to_thread(
                self.amazon.search_products,
                keywords=product_query
            )
        )
        tasks.append(("amazon", amazon_task))
        
        # Wait for all tasks
        results = {}
        for source, task in tasks:
            try:
                results[source] = await task
            except Exception as e:
                print(f"Error fetching from {source}: {e}")
                results[source] = []
        
        # Combine and analyze
        all_prices = []
        
        # Add eBay prices
        for item in results.get("ebay", []):
            all_prices.append({
                "price": item["price"],
                "source": "eBay Sold",
                "confidence": 0.9,  # Sold prices are highly reliable
                "date": item["end_time"]
            })
        
        # Add Amazon prices (with condition adjustment if needed)
        condition_multiplier = {
            "New": 1.0,
            "Like New": 0.95,
            "Good": 0.85,
            "Fair": 0.70,
            "Poor": 0.50
        }.get(condition, 0.85)
        
        for item in results.get("amazon", []):
            adjusted_price = item["price"] * condition_multiplier
            all_prices.append({
                "price": adjusted_price,
                "source": "Amazon (adjusted)",
                "confidence": 0.7,
                "date": "current"
            })
        
        return all_prices


# Usage
researcher = MultiSourcePriceResearcher(
    ebay_app_id="YOUR_EBAY_APP_ID",
    amazon_keys={
        "access_key": "YOUR_AMAZON_KEY",
        "secret_key": "YOUR_AMAZON_SECRET",
        "partner_tag": "YOUR_TAG"
    }
)

prices = await researcher.research_comprehensive(
    product_query="Vissani 7.2 cu ft refrigerator",
    condition="Fair"
)

# Calculate weighted average
if prices:
    weighted_sum = sum(p["price"] * p["confidence"] for p in prices)
    weight_total = sum(p["confidence"] for p in prices)
    weighted_avg = weighted_sum / weight_total
    
    print(f"Weighted average price: ${weighted_avg:.2f}")
    print(f"Based on {len(prices)} data points")
```

---

## 7. Rate Limiting and Best Practices

```python
import time
from functools import wraps
from collections import deque

class RateLimiter:
    """Rate limiter for API calls"""
    
    def __init__(self, calls_per_second: int = 5):
        self.calls_per_second = calls_per_second
        self.interval = 1.0 / calls_per_second
        self.last_call = 0
    
    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Wait if necessary
            elapsed = time.time() - self.last_call
            if elapsed < self.interval:
                time.sleep(self.interval - elapsed)
            
            self.last_call = time.time()
            return func(*args, **kwargs)
        
        return wrapper


class APICache:
    """Cache API responses to reduce calls"""
    
    def __init__(self, ttl_seconds: int = 3600):
        self.cache = {}
        self.ttl = ttl_seconds
    
    def get(self, key: str):
        """Get cached value if not expired"""
        if key in self.cache:
            value, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                return value
            else:
                del self.cache[key]
        return None
    
    def set(self, key: str, value):
        """Cache a value"""
        self.cache[key] = (value, time.time())


# Usage
@RateLimiter(calls_per_second=2)  # Max 2 calls per second
def make_api_call(url):
    return requests.get(url)
```

---

## 8. Cost Considerations

### API Pricing (as of 2026)

**eBay Finding API:**
- Free tier: 5,000 calls/day
- Commercial: $0.10 per 1,000 calls
- **Cost for 1,000 items: ~$0.10**

**Amazon Product Advertising API:**
- Free with affiliate program
- Must generate 3 sales/180 days to maintain access
- **Cost: Free (with requirements)**

**Keepa:**
- Tokens: 1 token = $0.002
- Price history: ~2 tokens per product
- **Cost for 1,000 items: ~$4.00**

**Estimated Total Cost:**
- Per 1,000 auction items analyzed: **$5-10**
- If analyzing 100 items/day: **$0.50-1.00/day** = **$15-30/month**

---

## Next Steps

1. **Start with eBay Finding API** - Free and most reliable
2. **Add Amazon for new product benchmarking**
3. **Use Keepa for price trend analysis** (optional but valuable)
4. **Implement caching** to reduce API costs
5. **Monitor API usage** and set budgets
6. **Scale gradually** - test with small batches first

This API infrastructure will provide accurate, real-time market data for your auction analysis system.
