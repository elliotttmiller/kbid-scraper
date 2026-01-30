# K-BID Auction Scraper

A comprehensive, fully autonomous web scraper for extracting all live auction listings and item details from k-bid.com.

## Features

✅ **Fully Autonomous** - Automatically discovers and scrapes all live auctions
✅ **Complete Data Extraction** - Gets all item details, bids, descriptions, images
✅ **Handles Pagination** - Automatically processes multi-page listings
✅ **CSV Export** - Clean, structured data export
✅ **Robust Error Handling** - Continues scraping even if individual items fail
✅ **Respectful Scraping** - Configurable delays between requests
✅ **Detailed Logging** - Full session logs and summary reports
✅ **Progress Tracking** - Real-time status updates during scraping

## What Gets Scraped

### Auction-Level Data
- Auction title and ID
- Auction house/affiliate name
- Location and contact phone
- Closing date/time
- Total number of items
- Categories
- Auction URL

### Item-Level Data
- Lot number
- Item title/description
- Current bid amount
- Next required bid
- High bidder information
- Item category
- Item closing time
- Item URL
- Image URL
- Short description (when available)

## Requirements

- Python 3.7 or higher
- Internet connection
- The following Python packages:
  - requests
  - beautifulsoup4

## Installation

### Step 1: Install Python
If you don't have Python installed:
- **Windows**: Download from [python.org](https://www.python.org/downloads/)
- **Mac**: `brew install python3` (if you have Homebrew)
- **Linux**: Usually pre-installed, or `sudo apt-get install python3`

### Step 2: Install Required Packages

Open a terminal/command prompt and run:

```bash
pip install requests beautifulsoup4
```

Or use the requirements file:

```bash
pip install -r requirements.txt
```

### Step 3: Download the Scraper

Save the `kbid_scraper.py` file to your computer.

## Usage

### Basic Usage

Simply run the scraper:

```bash
python kbid_scraper.py
```

You'll be prompted for:
1. **Delay between requests** (default: 1.0 second) - Lower values = faster but less respectful
2. **Output filename** (default: kbid_auctions_data.csv)

Then the scraper will automatically:
1. Find all auction listing pages
2. Extract all auction URLs
3. Scrape every item from every auction
4. Save everything to CSV

### Advanced Usage

You can also import and use the scraper in your own Python scripts:

```python
from kbid_scraper import KBidScraper

# Create scraper with 2-second delay
scraper = KBidScraper(delay=2.0)

# Run the scraper
scraper.scrape_all_auctions()

# Save to custom filename
scraper.save_to_csv('my_custom_output.csv')

# Save summary report
scraper.save_summary('my_summary.txt')
```

### Customization Options

You can customize the scraper by modifying the `delay` parameter:

```python
# Faster scraping (less respectful)
scraper = KBidScraper(delay=0.5)

# Slower scraping (more respectful)
scraper = KBidScraper(delay=2.0)
```

## Output Files

The scraper generates three files:

### 1. kbid_auctions_data.csv
Main data file containing all scraped items with the following columns:

| Column | Description |
|--------|-------------|
| lot_number | Auction lot number |
| item_title | Item name/description |
| short_description | Brief item description |
| current_bid | Current bid amount |
| next_required_bid | Minimum next bid |
| high_bidder | Current high bidder ID |
| category | Item category |
| item_closing_time | When this item closes |
| item_url | Direct link to item page |
| image_url | Item image URL |
| auction_id | Parent auction ID |
| auction_title | Parent auction name |
| affiliate | Auctioneer/affiliate name |
| location | Auction location |
| phone | Contact phone |
| closing_date | Auction closing date |
| total_items | Total items in auction |
| categories | All auction categories |
| auction_url | Auction page URL |

### 2. scraper_summary.txt
Summary statistics:
- Start and end times
- Total auctions processed
- Total items scraped
- Error count
- Average items per auction

### 3. kbid_scraper.log
Detailed execution log with:
- All requests made
- Errors encountered
- Progress updates
- Timestamps

## Example Output

Here's what the CSV data looks like:

```csv
lot_number,item_title,current_bid,next_required_bid,high_bidder,category,item_closing_time,...
1,Scottsdale Mint Stacker 10 ounce Silver Bar,1017.00,1092.00,#121153,Precious Metals,Today 05:00 pm,...
2,$100 1990 Federal Reserve Note Cleveland,163.00,173.00,#510579,Currency,Today 05:01 pm,...
3,1987 Silver Eagle - 99.9% pure silver,125.00,130.00,#399175,Coins,Today 05:03 pm,...
```

## Performance

Typical performance (with 1-second delay):
- **~50 auctions**: 10-15 minutes
- **~134 auctions**: 20-30 minutes
- **~500+ items/auction**: Proportionally longer

The scraper processes approximately:
- 60 requests per minute (1-second delay)
- 3,600 requests per hour

## Error Handling

The scraper is designed to be robust:
- **Network errors**: Retries and continues
- **Missing data**: Uses "N/A" placeholders
- **Invalid HTML**: Skips problematic items
- **Pagination errors**: Stops gracefully

All errors are logged to `kbid_scraper.log` for review.

## Best Practices

1. **Be Respectful**: Use a delay of at least 1 second
2. **Run During Off-Hours**: Less load on the website
3. **Check Logs**: Review `kbid_scraper.log` for any issues
4. **Verify Data**: Spot-check the CSV output
5. **Update Regularly**: Website structure may change over time

## Troubleshooting

### Problem: "No module named 'requests'"
**Solution**: Install required packages:
```bash
pip install requests beautifulsoup4
```

### Problem: "Connection Error" or "Timeout"
**Solution**: 
- Check your internet connection
- Try increasing the delay
- Website might be temporarily down

### Problem: "No data to save"
**Solution**:
- Check if k-bid.com is accessible
- Verify the website structure hasn't changed
- Check `kbid_scraper.log` for specific errors

### Problem: Scraper is too slow
**Solution**:
- Decrease the delay (e.g., `delay=0.5`)
- Note: This is less respectful to the server

### Problem: Getting blocked or rate-limited
**Solution**:
- Increase the delay (e.g., `delay=2.0`)
- Run during off-peak hours
- Take breaks between scraping sessions

## Legal and Ethical Considerations

⚠️ **Important**: Always respect the website's terms of service and robots.txt file.

This scraper:
- ✅ Uses reasonable delays between requests
- ✅ Identifies itself with a User-Agent
- ✅ Only accesses publicly available data
- ✅ Does not attempt to bypass security measures

**You should**:
- Review k-bid.com's terms of service
- Use the scraped data responsibly
- Not overwhelm their servers with requests
- Consider contacting them if doing large-scale scraping

## Maintenance

Website structures change over time. If the scraper stops working:

1. Check if k-bid.com has updated their HTML structure
2. Review the error logs
3. Update the CSS selectors or XPath expressions
4. Test with a single auction first

## Support

If you encounter issues:
1. Check the log file (`kbid_scraper.log`)
2. Review the error messages
3. Verify your Python version (`python --version`)
4. Ensure all dependencies are installed

## License

This scraper is provided as-is for educational purposes. Use responsibly and in accordance with applicable laws and website terms of service.

## Changelog

### Version 1.0 (January 2026)
- Initial release
- Full auction and item scraping
- CSV export functionality
- Comprehensive error handling
- Logging and summary reports
