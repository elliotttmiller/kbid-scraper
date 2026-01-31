"""
K-Bid Diagnostic Test Script
=============================
This script tests fetching a single item page to see what data is actually available.
Use this to diagnose extraction issues before running full scraper.
"""

import os
import requests
from bs4 import BeautifulSoup
import re
import json

def test_item_page(item_url):
    """Test fetching and parsing a single item page"""
    
    print(f"\n{'='*80}")
    print(f"Testing URL: {item_url}")
    print(f"{'='*80}\n")
    
    # Setup session
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    })
    
    try:
        # Fetch page
        print("Fetching page...")
        response = session.get(item_url, timeout=15)
        response.raise_for_status()
        print(f"Status code: {response.status_code}")
        print(f"Content length: {len(response.content)} bytes\n")
        
        # Parse
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Save raw HTML for inspection (use local results/diagnostics folder)
        results_dir = os.path.join(os.getcwd(), 'results', 'diagnostics')
        os.makedirs(results_dir, exist_ok=True)
        html_path = os.path.join(results_dir, 'test_item_page.html')
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(soup.prettify())
        print(f"✓ Saved raw HTML to: {html_path}\n")
        
        # Test extraction
        results = {}
        
        # === TITLE ===
        print("Testing TITLE extraction:")
        title_methods = {
            'h1': soup.find('h1'),
            'h2': soup.find('h2'),
            'meta_og_title': soup.find('meta', property='og:title'),
            'title_tag': soup.find('title')
        }
        for method, elem in title_methods.items():
            if elem:
                text = elem.get('content') if method == 'meta_og_title' else elem.get_text(strip=True)
                print(f"  {method}: {text[:100]}")
                if 'title' not in results:
                    results['title'] = text
        print()
        
        # === CURRENT BID ===
        print("Testing CURRENT BID extraction:")
        
        # Method 1: ID pattern
        bid_elem = soup.find('span', id=re.compile(r'lot_current_bid_lot_k-bid'))
        if bid_elem:
            print(f"  ✓ Found via ID pattern: {bid_elem.get('id')}")
            print(f"    Value: {bid_elem.get_text(strip=True)}")
            results['current_bid'] = bid_elem.get_text(strip=True)
        else:
            print(f"  ✗ ID pattern not found")
        
        # Method 2: Class
        bid_class = soup.find('span', class_='lot-current-bid')
        if bid_class:
            print(f"  ✓ Found via class: {bid_class.get_text(strip=True)}")
            if 'current_bid' not in results:
                results['current_bid'] = bid_class.get_text(strip=True)
        else:
            print(f"  ✗ Class 'lot-current-bid' not found")
        
        # Method 3: Text search
        bid_label = soup.find(string=re.compile(r'Current\s*Bid', re.I))
        if bid_label:
            print(f"  ✓ Found 'Current Bid' label")
            parent = bid_label.find_parent()
            if parent:
                # Search for dollar amounts nearby
                for elem in parent.find_all(['span', 'strong', 'h2']):
                    text = elem.get_text(strip=True)
                    if '$' in text:
                        print(f"    Found nearby: {text}")
                        if 'current_bid' not in results:
                            results['current_bid'] = text
                        break
        else:
            print(f"  ✗ 'Current Bid' label not found")
        print()
        
        # === NEXT REQUIRED BID ===
        print("Testing NEXT REQUIRED BID extraction:")
        next_elem = soup.find('span', id=re.compile(r'lot_next_required_bid_lot_k-bid'))
        if next_elem:
            print(f"  ✓ Found via ID pattern: {next_elem.get_text(strip=True)}")
            results['next_required_bid'] = next_elem.get_text(strip=True)
        else:
            print(f"  ✗ ID pattern not found")
        print()
        
        # === HIGH BIDDER ===
        print("Testing HIGH BIDDER extraction:")
        bidder_elem = soup.find('span', id=re.compile(r'lot_current_high_bidder_detail_lot_k-bid'))
        if bidder_elem:
            print(f"  ✓ Found via ID pattern: {bidder_elem.get_text(strip=True)}")
            results['high_bidder'] = bidder_elem.get_text(strip=True)
        else:
            print(f"  ✗ ID pattern not found")
        print()
        
        # === CHECK FOR "NO LONGER AVAILABLE" MESSAGE ===
        print("Checking for error messages:")
        unavailable = soup.find(string=re.compile(r'no longer available', re.I))
        if unavailable:
            print(f"  ⚠ WARNING: Found 'no longer available' message")
            results['status'] = 'unavailable'
        else:
            print(f"  ✓ No 'unavailable' message found")
            results['status'] = 'active'
        print()
        
        # === DESCRIPTION ===
        print("Testing DESCRIPTION extraction:")
        desc_elem = soup.find('div', class_=re.compile(r'lot.*desc', re.I))
        if desc_elem:
            desc_text = desc_elem.get_text(strip=True)[:200]
            print(f"  ✓ Found description: {desc_text}...")
            results['description'] = desc_text
        else:
            print(f"  ✗ Description not found")
        print()
        
        # === IMAGE ===
        print("Testing IMAGE extraction:")
        img_elem = soup.find('img', class_=re.compile(r'galleria', re.I))
        if img_elem:
            print(f"  ✓ Found image: {img_elem.get('src', '')[:100]}")
            results['image'] = img_elem.get('src')
        else:
            meta_img = soup.find('meta', property='og:image')
            if meta_img:
                print(f"  ✓ Found via meta tag: {meta_img.get('content', '')[:100]}")
                results['image'] = meta_img.get('content')
            else:
                print(f"  ✗ Image not found")
        print()
        
        # === SUMMARY ===
        print(f"\n{'='*80}")
        print("EXTRACTION RESULTS SUMMARY:")
        print(f"{'='*80}\n")
        print(json.dumps(results, indent=2))
        
        # Save results (JSON)
        json_path = os.path.join(results_dir, 'test_results.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        print(f"\n✓ Saved results to: {json_path}")
        
        # Check if this is a valid item
        if results.get('status') == 'unavailable':
            print("\n⚠ WARNING: This item appears to be no longer available!")
            print("Try testing with a different item URL that's currently active.")
        elif 'current_bid' in results and results['current_bid'] != '0.00':
            print(f"\n✓ SUCCESS: Found bid data! Current bid: {results['current_bid']}")
        elif 'current_bid' not in results:
            print(f"\n✗ PROBLEM: Could not extract current bid")
            print("The page structure might be different than expected.")
        else:
            print(f"\n? Item has no bids yet (current_bid is 0.00 or empty)")
        
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Run diagnostic test"""
    print("\n" + "="*80)
    print("K-BID ITEM PAGE DIAGNOSTIC TEST")
    print("="*80)
    print("\nThis script tests fetching a single item to diagnose extraction issues.")
    print("\nEnter a K-Bid item URL to test (or press Enter for default):")
    print("Example: https://www.k-bid.com/auction/62961/item/2")
    
    url = input("\nURL: ").strip()
    
    if not url:
        # Default test URL (item 2 from your data)
        url = "https://www.k-bid.com/auction/62961/item/2"
        print(f"Using default URL: {url}")
    
    test_item_page(url)
    
    print(f"\n{'='*80}")
    print("DIAGNOSTIC COMPLETE")
    print(f"{'='*80}")
    print(f"\nCheck these output files (in results/diagnostics):")
    print("  - test_item_page.html (raw HTML for manual inspection)")
    print("  - test_results.json (extracted data)")
    print("\nIf the item is 'no longer available', try a different item URL.")
    print("If bid data is found, the scraper should work correctly.")


if __name__ == "__main__":
    main()