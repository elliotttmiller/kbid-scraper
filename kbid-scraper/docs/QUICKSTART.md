# Quick Start Guide - K-BID Scraper

## 3-Minute Setup

### 1. Install Python
- Download from https://www.python.org/downloads/
- During installation, CHECK "Add Python to PATH"

### 2. Install Dependencies
Open Terminal/Command Prompt and run:
```bash
pip install requests beautifulsoup4
```

### 3. Run the Scraper
```bash
python kbid_scraper.py
```

That's it! The scraper will automatically:
- Find all live auctions on k-bid.com
- Extract all item details
- Save everything to `kbid_auctions_data.csv`

## What You'll Get

A CSV file with EVERY auction item including:
- Item title and description
- Current bid and next required bid
- Category and lot number
- Auction details (location, closing time, etc.)
- Image URLs
- Direct links to items

## Expected Time

For ~134 auctions with ~15,000+ items:
- **With 1-second delay**: ~30-45 minutes
- **With 0.5-second delay**: ~15-25 minutes (less respectful)
- **With 2-second delay**: ~60-90 minutes (more respectful)

## Watching Progress

The scraper shows you:
```
[1/134] Processing auction...
  URL: https://www.k-bid.com/auction/62908
  Title: Tax Exempt Constitutional Currency Auction...
  Affiliate: Hairy Mosquito Trading Co.
  Items: 383
  Page 1: Processing 50 items...
  Page 2: Processing 50 items...
  ...
  ✓ Total items scraped from this auction: 383
```

## Customization

### Change the delay (default is 1 second):
When prompted, enter your preferred delay:
- `0.5` = Faster but less respectful
- `1.0` = Balanced (recommended)
- `2.0` = Slower but more respectful

### Change the output filename:
When prompted, enter your preferred name:
- `my_data.csv`
- `kbid_january_2026.csv`
- etc.

## Troubleshooting

### "Command 'python' not found"
Try `python3` instead:
```bash
python3 kbid_scraper.py
```

### "No module named 'requests'"
Install dependencies:
```bash
pip install requests beautifulsoup4
```
or
```bash
pip3 install requests beautifulsoup4
```

### Scraper taking too long?
- Press Ctrl+C to stop
- Reduce the delay in the prompt
- Run again

### No data in CSV?
- Check `kbid_scraper.log` for errors
- Verify internet connection
- Try running during different hours

## Opening the CSV File

### In Excel:
1. Double-click the CSV file
2. Or: Excel → Open → Select CSV file

### In Google Sheets:
1. File → Import
2. Upload → Select CSV file
3. Click "Import data"

### In Python/Pandas:
```python
import pandas as pd
df = pd.read_csv('kbid_auctions_data.csv')
print(df.head())
```

## Next Steps

After scraping:
1. **Open the CSV** - Review your data
2. **Check the summary** - See statistics in `scraper_summary.txt`
3. **Review logs** - Any errors in `kbid_scraper.log`

## Tips for Best Results

✅ Run during off-peak hours (late night/early morning)
✅ Use at least 1-second delay
✅ Let it complete fully (don't interrupt)
✅ Check a few rows of data to verify quality
✅ Save the log files for reference

## Need More Help?

Check `README.md` for:
- Detailed documentation
- Advanced usage examples
- Full feature list
- Error handling guide
- Performance optimization

---

**Remember**: Be respectful of the k-bid.com servers. Use reasonable delays and don't run the scraper too frequently.
