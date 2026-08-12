"""
Advanced Usage Examples for K-BID Scraper

This file demonstrates various ways to use the scraper
for different needs and use cases.
"""

import os
import sys

# Ensure local package import
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import scraper_enhanced as se
KBidScraper = se.KBidScraperFixed

import pandas as pd
from datetime import datetime


# ============================================================================
# EXAMPLE 1: Basic scraping with custom settings
# ============================================================================

def example_1_basic_scraping():
    """Basic scraping with custom delay and filename"""
    print("\n" + "="*80)
    print("EXAMPLE 1: Basic Scraping")
    print("="*80)
    
    # Create scraper with 2-second delay (more respectful)
    scraper = KBidScraper(delay=2.0)
    
    # Run the scraper
    scraper.scrape_all_auctions()
    
    # Save to custom filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'kbid_data_{timestamp}.csv'
    scraper.save_to_csv(filename)
    scraper.save_summary(f'summary_{timestamp}.txt')
    
    print(f"\nData saved to: {filename}")


# ============================================================================
# EXAMPLE 2: Filter and analyze specific auctions
# ============================================================================

def example_2_filter_by_affiliate():
    """Scrape all, then filter for specific auctioneer"""
    print("\n" + "="*80)
    print("EXAMPLE 2: Filter by Affiliate")
    print("="*80)
    
    scraper = KBidScraper(delay=1.0)
    scraper.scrape_all_auctions()
    
    # Save all data
    scraper.save_to_csv('kbid_all_data.csv')
    
    # Load with pandas and filter
    df = pd.read_csv('kbid_all_data.csv')
    
    # Filter for specific affiliate
    target_affiliate = "Hairy Mosquito Trading Co."
    filtered = df[df['affiliate'] == target_affiliate]
    
    # Save filtered data
    filtered.to_csv('kbid_hairy_mosquito_only.csv', index=False)
    
    print(f"\nFiltered {len(filtered)} items from {target_affiliate}")
    print(f"Saved to: kbid_hairy_mosquito_only.csv")


# ============================================================================
# EXAMPLE 3: Extract only high-value items
# ============================================================================

def example_3_high_value_items():
    """Get only items with bids over a certain amount"""
    print("\n" + "="*80)
    print("EXAMPLE 3: High-Value Items Only")
    print("="*80)
    
    scraper = KBidScraper(delay=1.0)
    scraper.scrape_all_auctions()
    scraper.save_to_csv('kbid_all_data.csv')
    
    # Load and filter
    df = pd.read_csv('kbid_all_data.csv')
    
    # Convert bid to numeric (remove commas, handle NaN)
    df['current_bid'] = pd.to_numeric(df['current_bid'], errors='coerce')
    
    # Filter for items with bids over $500
    high_value = df[df['current_bid'] > 500].copy()
    
    # Sort by bid amount (highest first)
    high_value = high_value.sort_values('current_bid', ascending=False)
    
    # Save
    high_value.to_csv('kbid_high_value_items.csv', index=False)
    
    print(f"\nFound {len(high_value)} items with bids over $500")
    print(f"Highest bid: ${high_value['current_bid'].max():.2f}")
    print(f"Saved to: kbid_high_value_items.csv")


# ============================================================================
# EXAMPLE 4: Category analysis
# ============================================================================

def example_4_category_breakdown():
    """Analyze items by category"""
    print("\n" + "="*80)
    print("EXAMPLE 4: Category Analysis")
    print("="*80)
    
    scraper = KBidScraper(delay=1.0)
    scraper.scrape_all_auctions()
    scraper.save_to_csv('kbid_all_data.csv')
    
    # Load data
    df = pd.read_csv('kbid_all_data.csv')
    
    # Count items by category
    category_counts = df['category'].value_counts()
    
    # Convert current_bid to numeric for analysis
    df['current_bid'] = pd.to_numeric(df['current_bid'], errors='coerce')
    
    # Calculate total bid value by category
    category_values = df.groupby('category')['current_bid'].sum().sort_values(ascending=False)
    
    # Save category report
    with open('category_analysis.txt', 'w') as f:
        f.write("K-BID CATEGORY ANALYSIS\n")
        f.write("=" * 80 + "\n\n")
        
        f.write("ITEMS PER CATEGORY:\n")
        f.write("-" * 80 + "\n")
        for cat, count in category_counts.items():
            f.write(f"{cat}: {count} items\n")
        
        f.write("\n\nTOTAL BID VALUE BY CATEGORY:\n")
        f.write("-" * 80 + "\n")
        for cat, value in category_values.items():
            f.write(f"{cat}: ${value:,.2f}\n")
    
    print("\nCategory analysis saved to: category_analysis.txt")
    print(f"\nTop 5 categories by item count:")
    print(category_counts.head())


# ============================================================================
# EXAMPLE 5: Monitor specific search terms
# ============================================================================

def example_5_search_keywords():
    """Find items matching specific keywords"""
    print("\n" + "="*80)
    print("EXAMPLE 5: Search for Keywords")
    print("="*80)
    
    # Keywords to search for
    keywords = ['silver', 'gold', 'antique', 'vintage']
    
    scraper = KBidScraper(delay=1.0)
    scraper.scrape_all_auctions()
    scraper.save_to_csv('kbid_all_data.csv')
    
    # Load data
    df = pd.read_csv('kbid_all_data.csv')
    
    # Search in title for keywords
    for keyword in keywords:
        matches = df[df['item_title'].str.contains(keyword, case=False, na=False)]
        
        if len(matches) > 0:
            filename = f'kbid_{keyword}_items.csv'
            matches.to_csv(filename, index=False)
            print(f"\nFound {len(matches)} items matching '{keyword}'")
            print(f"Saved to: {filename}")


# ============================================================================
# EXAMPLE 6: Closing soon alerts
# ============================================================================

def example_6_closing_soon():
    """Find items closing today"""
    print("\n" + "="*80)
    print("EXAMPLE 6: Items Closing Today")
    print("="*80)
    
    scraper = KBidScraper(delay=1.0)
    scraper.scrape_all_auctions()
    scraper.save_to_csv('kbid_all_data.csv')
    
    # Load data
    df = pd.read_csv('kbid_all_data.csv')
    
    # Filter for items closing today
    today_items = df[df['item_closing_time'].str.contains('Today', case=False, na=False)]
    
    # Convert bid to numeric and sort by value
    today_items['current_bid'] = pd.to_numeric(today_items['current_bid'], errors='coerce')
    today_items = today_items.sort_values('current_bid', ascending=False)
    
    # Save
    today_items.to_csv('kbid_closing_today.csv', index=False)
    
    print(f"\nFound {len(today_items)} items closing today")
    print(f"Highest current bid: ${today_items['current_bid'].max():.2f}")
    print(f"Saved to: kbid_closing_today.csv")


# ============================================================================
# EXAMPLE 7: Export to multiple formats
# ============================================================================

def example_7_multiple_formats():
    """Export data to CSV, Excel, and JSON"""
    print("\n" + "="*80)
    print("EXAMPLE 7: Multiple Export Formats")
    print("="*80)
    
    scraper = KBidScraper(delay=1.0)
    scraper.scrape_all_auctions()
    
    # Save to CSV (default)
    scraper.save_to_csv('kbid_data.csv')
    
    # Load with pandas
    df = pd.read_csv('kbid_data.csv')
    
    # Save to Excel (requires openpyxl: pip install openpyxl)
    try:
        df.to_excel('kbid_data.xlsx', index=False)
        print("✓ Saved to Excel: kbid_data.xlsx")
    except ImportError:
        print("⚠ Excel export requires: pip install openpyxl")
    
    # Save to JSON
    df.to_json('kbid_data.json', orient='records', indent=2)
    print("✓ Saved to JSON: kbid_data.json")
    
    # Save to HTML table
    df.to_html('kbid_data.html', index=False)
    print("✓ Saved to HTML: kbid_data.html")


# ============================================================================
# EXAMPLE 8: Generate auction summary report
# ============================================================================

def example_8_auction_summary():
    """Create detailed summary of all auctions"""
    print("\n" + "="*80)
    print("EXAMPLE 8: Auction Summary Report")
    print("="*80)
    
    scraper = KBidScraper(delay=1.0)
    scraper.scrape_all_auctions()
    scraper.save_to_csv('kbid_all_data.csv')
    
    df = pd.read_csv('kbid_all_data.csv')
    df['current_bid'] = pd.to_numeric(df['current_bid'], errors='coerce')
    
    # Group by auction
    auction_summary = df.groupby(['auction_id', 'auction_title', 'affiliate']).agg({
        'lot_number': 'count',
        'current_bid': ['sum', 'mean', 'max'],
        'high_bidder': lambda x: (x != 'No bids').sum()  # Count items with bids
    }).round(2)
    
    # Rename columns
    auction_summary.columns = ['Total_Items', 'Total_Bid_Value', 'Avg_Bid', 'Max_Bid', 'Items_With_Bids']
    
    # Save
    auction_summary.to_csv('auction_summary.csv')
    
    print("\nAuction summary saved to: auction_summary.csv")
    print(f"\nTotal auctions: {len(auction_summary)}")
    print(f"Total items: {auction_summary['Total_Items'].sum():.0f}")
    print(f"Total bid value: ${auction_summary['Total_Bid_Value'].sum():,.2f}")


# ============================================================================
# EXAMPLE 9: Update existing data (incremental scrape)
# ============================================================================

def example_9_incremental_update():
    """
    Scrape only new auctions (useful for regular monitoring)
    Note: This is a simplified example - you'd need to implement
    proper auction ID tracking for production use
    """
    print("\n" + "="*80)
    print("EXAMPLE 9: Incremental Update")
    print("="*80)
    
    import os
    
    # Check if we have previous data
    if os.path.exists('kbid_all_data.csv'):
        print("Found existing data file")
        df_old = pd.read_csv('kbid_all_data.csv')
        old_auction_ids = set(df_old['auction_id'].unique())
        print(f"Previous auctions: {len(old_auction_ids)}")
    else:
        print("No existing data, performing full scrape")
        old_auction_ids = set()
    
    # Scrape current auctions
    scraper = KBidScraper(delay=1.0)
    scraper.scrape_all_auctions()
    scraper.save_to_csv('kbid_latest.csv')
    
    # Load new data
    df_new = pd.read_csv('kbid_latest.csv')
    new_auction_ids = set(df_new['auction_id'].unique())
    
    # Find truly new auctions
    newly_added = new_auction_ids - old_auction_ids
    
    if newly_added:
        print(f"\nFound {len(newly_added)} new auctions!")
        new_items = df_new[df_new['auction_id'].isin(newly_added)]
        new_items.to_csv('kbid_new_auctions.csv', index=False)
        print(f"New items saved to: kbid_new_auctions.csv")
    else:
        print("\nNo new auctions found")


# ============================================================================
# EXAMPLE 10: Custom item filter function
# ============================================================================

def example_10_custom_filter():
    """
    Use custom filtering logic to find specific types of items
    """
    print("\n" + "="*80)
    print("EXAMPLE 10: Custom Filtering")
    print("="*80)
    
    scraper = KBidScraper(delay=1.0)
    scraper.scrape_all_auctions()
    scraper.save_to_csv('kbid_all_data.csv')
    
    df = pd.read_csv('kbid_all_data.csv')
    df['current_bid'] = pd.to_numeric(df['current_bid'], errors='coerce')
    
    # Custom filter: Coins/Currency with high bids
    custom_filter = (
        (df['category'].str.contains('Coin|Currency', case=False, na=False)) &
        (df['current_bid'] > 100) &
        (df['high_bidder'] != 'No bids')
    )
    
    filtered_items = df[custom_filter].copy()
    filtered_items = filtered_items.sort_values('current_bid', ascending=False)
    
    filtered_items.to_csv('kbid_hot_coins.csv', index=False)
    
    print(f"\nFound {len(filtered_items)} coins/currency items with bids over $100")
    print(f"Saved to: kbid_hot_coins.csv")
    
    if len(filtered_items) > 0:
        print(f"\nTop 5 items:")
        print(filtered_items[['item_title', 'current_bid', 'auction_title']].head())


# ============================================================================
# Run examples
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*80)
    print("K-BID SCRAPER - ADVANCED USAGE EXAMPLES")
    print("="*80)
    print("\nChoose an example to run:\n")
    
    examples = [
        ("Basic scraping with custom settings", example_1_basic_scraping),
        ("Filter by affiliate/auctioneer", example_2_filter_by_affiliate),
        ("Extract high-value items only", example_3_high_value_items),
        ("Category analysis", example_4_category_breakdown),
        ("Search for keywords", example_5_search_keywords),
        ("Items closing today", example_6_closing_soon),
        ("Export to multiple formats", example_7_multiple_formats),
        ("Generate auction summary", example_8_auction_summary),
        ("Incremental update", example_9_incremental_update),
        ("Custom filtering", example_10_custom_filter),
    ]
    
    for i, (desc, _) in enumerate(examples, 1):
        print(f"{i:2d}. {desc}")
    
    print(f"{len(examples)+1:2d}. Run all examples")
    print(" 0. Exit")
    
    try:
        choice = int(input("\nEnter your choice: "))
        
        if choice == 0:
            print("Exiting...")
        elif 1 <= choice <= len(examples):
            examples[choice-1][1]()
        elif choice == len(examples) + 1:
            print("\nRunning all examples (this will take a while)...\n")
            for desc, func in examples:
                func()
        else:
            print("Invalid choice!")
            
    except ValueError:
        print("Invalid input!")
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\nError: {e}")
