# K-BID Auction Scraper - Complete Package

## 📦 What's Included

This complete package contains everything you need to scrape all auction data from k-bid.com:

### Core Files:
1. **kbid_scraper.py** - Main scraper program (fully autonomous)
2. **requirements.txt** - Python dependencies
3. **README.md** - Complete documentation
4. **QUICKSTART.md** - 3-minute setup guide
5. **advanced_examples.py** - 10 usage examples
6. **SETUP_GUIDE.md** - This file

---

## 🚀 Complete Setup Instructions

### Windows Setup

#### Step 1: Install Python
1. Go to https://www.python.org/downloads/
2. Download Python 3.10 or newer
3. Run the installer
4. ⚠️ **IMPORTANT**: Check "Add Python to PATH" during installation
5. Click "Install Now"

#### Step 2: Verify Installation
Open Command Prompt (search for "cmd") and type:
```cmd
python --version
```
Should show: `Python 3.x.x`

#### Step 3: Install Dependencies
In Command Prompt:
```cmd
pip install requests beautifulsoup4
```

Or navigate to the folder with the scraper files and run:
```cmd
pip install -r requirements.txt
```

#### Step 4: Run the Scraper
```cmd
python kbid_scraper.py
```

---

### Mac Setup

#### Step 1: Install Python
Mac comes with Python, but you should install the latest version:

**Option A - Using Homebrew (recommended):**
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install python3
```

**Option B - Direct download:**
1. Go to https://www.python.org/downloads/
2. Download the macOS installer
3. Run the installer

#### Step 2: Verify Installation
Open Terminal and type:
```bash
python3 --version
```

#### Step 3: Install Dependencies
```bash
pip3 install requests beautifulsoup4
```

Or:
```bash
pip3 install -r requirements.txt
```

#### Step 4: Run the Scraper
```bash
python3 kbid_scraper.py
```

---

### Linux Setup

#### Step 1: Install Python (if not already installed)
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3 python3-pip

# Fedora
sudo dnf install python3 python3-pip

# Arch
sudo pacman -S python python-pip
```

#### Step 2: Verify Installation
```bash
python3 --version
```

#### Step 3: Install Dependencies
```bash
pip3 install requests beautifulsoup4
```

Or:
```bash
pip3 install -r requirements.txt
```

#### Step 4: Run the Scraper
```bash
python3 kbid_scraper.py
```

---

## 🎯 Usage Scenarios

### Scenario 1: First Time User
**Goal**: Get all auction data quickly

```bash
python kbid_scraper.py
```
- Press Enter for default delay (1.0 seconds)
- Press Enter for default filename
- Wait for completion
- Open `kbid_auctions_data.csv` in Excel

**Expected time**: 30-45 minutes for ~134 auctions

---

### Scenario 2: Regular Monitoring
**Goal**: Check for new auctions daily

**Day 1**: Full scrape
```bash
python kbid_scraper.py
# Save as: kbid_day1.csv
```

**Day 2**: New scrape
```bash
python kbid_scraper.py
# Save as: kbid_day2.csv
```

Then compare files to see what's new:
```python
import pandas as pd

df1 = pd.read_csv('kbid_day1.csv')
df2 = pd.read_csv('kbid_day2.csv')

old_ids = set(df1['auction_id'])
new_ids = set(df2['auction_id'])
truly_new = new_ids - old_ids

print(f"New auctions: {len(truly_new)}")
```

---

### Scenario 3: Specific Category Focus
**Goal**: Only get coins and currency items

```bash
python kbid_scraper.py
# Let it complete, then:
```

```python
import pandas as pd

df = pd.read_csv('kbid_auctions_data.csv')
coins = df[df['category'].str.contains('Coin|Currency', case=False, na=False)]
coins.to_csv('coins_only.csv', index=False)
```

---

### Scenario 4: High-Value Monitoring
**Goal**: Alert on items over $1,000

```bash
python kbid_scraper.py
```

```python
import pandas as pd

df = pd.read_csv('kbid_auctions_data.csv')
df['current_bid'] = pd.to_numeric(df['current_bid'], errors='coerce')

high_value = df[df['current_bid'] > 1000].sort_values('current_bid', ascending=False)
high_value.to_csv('high_value_items.csv', index=False)

print(f"Found {len(high_value)} items over $1,000")
print(f"Highest: ${high_value['current_bid'].max():,.2f}")
```

---

## 📊 Working with the Data

### Opening in Excel

**Windows:**
```cmd
start kbid_auctions_data.csv
```

**Mac:**
```bash
open kbid_auctions_data.csv
```

**Linux:**
```bash
libreoffice kbid_auctions_data.csv
```

### Opening in Google Sheets
1. Go to sheets.google.com
2. File → Import
3. Upload → Browse → Select CSV
4. Import data

### Using Python/Pandas
```python
import pandas as pd

# Load data
df = pd.read_csv('kbid_auctions_data.csv')

# View first 5 rows
print(df.head())

# Basic statistics
print(df.describe())

# Count items per auction
print(df['auction_title'].value_counts())

# Total bid value
df['current_bid'] = pd.to_numeric(df['current_bid'], errors='coerce')
print(f"Total bid value: ${df['current_bid'].sum():,.2f}")
```

---

## 🔧 Customization Guide

### Adjust Scraping Speed

**Faster (less respectful):**
```python
from kbid_scraper import KBidScraper

scraper = KBidScraper(delay=0.5)  # Half second between requests
scraper.scrape_all_auctions()
scraper.save_to_csv()
```

**Slower (more respectful):**
```python
scraper = KBidScraper(delay=2.0)  # Two seconds between requests
scraper.scrape_all_auctions()
scraper.save_to_csv()
```

### Custom Output Format

**Add timestamp to filename:**
```python
from datetime import datetime
from kbid_scraper import KBidScraper

scraper = KBidScraper(delay=1.0)
scraper.scrape_all_auctions()

timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
scraper.save_to_csv(f'kbid_data_{timestamp}.csv')
```

### Filter During Scraping

**Only scrape specific auction IDs:**
```python
from kbid_scraper import KBidScraper

scraper = KBidScraper(delay=1.0)

# Manually specify auction URLs
target_auctions = [
    "https://www.k-bid.com/auction/62908",
    "https://www.k-bid.com/auction/63031",
]

for auction_url in target_auctions:
    auction_info = scraper.extract_auction_details(auction_url)
    if auction_info:
        items = scraper.get_all_items_from_auction(auction_url, auction_info)
        scraper.all_items.extend(items)

scraper.save_to_csv('specific_auctions.csv')
```

---

## 🐛 Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'requests'"

**Solution:**
```bash
pip install requests beautifulsoup4
```
or
```bash
pip3 install requests beautifulsoup4
```

---

### Issue: "python: command not found"

**Solution (Mac/Linux):**
Try `python3` instead:
```bash
python3 kbid_scraper.py
```

**Solution (Windows):**
Python wasn't added to PATH. Reinstall Python and check "Add to PATH" option.

---

### Issue: Scraper hangs or times out

**Possible causes:**
1. Network issues - Check internet connection
2. Website temporarily down - Try again later
3. Rate limiting - Increase delay

**Solution:**
```python
scraper = KBidScraper(delay=2.0)  # Increase delay
```

---

### Issue: Missing data in CSV (lots of "N/A")

**Possible causes:**
1. Website structure changed
2. Specific auctions have different HTML
3. Items haven't received bids yet

**Solution:**
- Check log file: `kbid_scraper.log`
- Verify on website manually
- "N/A" for no bids is expected

---

### Issue: Script stops with error halfway through

**Solution:**
The scraper is designed to continue on errors. Check:
1. `kbid_scraper.log` for specific errors
2. Partial data should still be saved
3. Re-run to complete

---

### Issue: CSV file is huge (>100MB)

**This is normal!** With 15,000+ items, the CSV will be large.

**Solutions:**
1. Split by auction:
```python
import pandas as pd
df = pd.read_csv('kbid_auctions_data.csv')
for auction_id in df['auction_id'].unique():
    auction_df = df[df['auction_id'] == auction_id]
    auction_df.to_csv(f'auction_{auction_id}.csv', index=False)
```

2. Use compression:
```python
df.to_csv('kbid_data.csv.gz', compression='gzip', index=False)
```

---

## 📅 Scheduled Scraping

### Windows (Task Scheduler)

1. Create a batch file `run_scraper.bat`:
```batch
@echo off
cd C:\path\to\scraper
python kbid_scraper.py
```

2. Open Task Scheduler
3. Create Basic Task
4. Set schedule (e.g., daily at 3 AM)
5. Action: Start a program
6. Program: `C:\path\to\run_scraper.bat`

### Mac (cron)

1. Create a shell script `run_scraper.sh`:
```bash
#!/bin/bash
cd /path/to/scraper
python3 kbid_scraper.py
```

2. Make it executable:
```bash
chmod +x run_scraper.sh
```

3. Edit crontab:
```bash
crontab -e
```

4. Add line (run daily at 3 AM):
```
0 3 * * * /path/to/run_scraper.sh
```

### Linux (cron) - Same as Mac

Or use systemd timer for more control.

---

## 🔐 Security & Privacy

### Best Practices:
1. ✅ Don't share the scraped data publicly
2. ✅ Respect k-bid.com's terms of service
3. ✅ Use reasonable delays (1+ second)
4. ✅ Don't run too frequently (max once per hour)
5. ✅ Check robots.txt: https://www.k-bid.com/robots.txt

### Data Storage:
- CSV files contain public auction data
- No personal bidder information (only IDs like "#121153")
- Images are URLs, not downloaded
- No login credentials are used or stored

---

## 📈 Performance Optimization

### Speed vs Respectfulness:

| Delay | Speed | Respectfulness | Recommendation |
|-------|-------|----------------|----------------|
| 0.5s  | Fast  | Low            | Not recommended |
| 1.0s  | Medium| Medium         | ✅ Recommended |
| 2.0s  | Slow  | High           | Very respectful |
| 5.0s  | Very slow | Very high  | Overkill |

### Optimize for large scrapes:
```python
# Use multiprocessing for post-processing, not scraping
import pandas as pd
from multiprocessing import Pool

def process_auction(auction_file):
    df = pd.read_csv(auction_file)
    # Process auction data
    return results

auction_files = ['auction_1.csv', 'auction_2.csv', ...]
with Pool(4) as p:
    results = p.map(process_auction, auction_files)
```

---

## 📚 Additional Resources

### Python Pandas Tutorial:
- https://pandas.pydata.org/docs/getting_started/tutorials.html

### Data Analysis Examples:
- See `advanced_examples.py` in this package

### Regular Expressions (for custom filters):
- https://regex101.com/

### CSV to Database Import:
```python
import pandas as pd
import sqlite3

# Create database
conn = sqlite3.connect('kbid_data.db')

# Import CSV
df = pd.read_csv('kbid_auctions_data.csv')
df.to_sql('auctions', conn, if_exists='replace', index=False)

# Query
query = "SELECT * FROM auctions WHERE current_bid > 1000"
results = pd.read_sql(query, conn)
```

---

## 🆘 Support

### Log Files:
Always check these first when issues occur:
1. `kbid_scraper.log` - Detailed execution log
2. `scraper_summary.txt` - Session statistics

### Common Commands:
```bash
# View last 50 lines of log
tail -n 50 kbid_scraper.log

# Search for errors in log
grep -i error kbid_scraper.log

# Count items in CSV
wc -l kbid_auctions_data.csv
```

### Testing:
Before running full scrape, test with a single auction:
```python
from kbid_scraper import KBidScraper

scraper = KBidScraper(delay=1.0)
auction_url = "https://www.k-bid.com/auction/62908"
auction_info = scraper.extract_auction_details(auction_url)
items = scraper.get_all_items_from_auction(auction_url, auction_info)
print(f"Scraped {len(items)} items")
```

---

## 📝 License & Legal

### Disclaimer:
This scraper is provided as-is for educational purposes. Users are responsible for:
- Complying with k-bid.com's terms of service
- Using the data ethically and legally
- Not overwhelming the website's servers
- Respecting intellectual property rights

### Attribution:
If you use this scraper for research or publications, please acknowledge:
- The scraper was created for educational purposes
- Data source: k-bid.com
- Scraper author: Claude (Anthropic)

---

## 🎓 Learning Path

### Beginner:
1. Run basic scraper with defaults
2. Open CSV in Excel
3. Explore the data
4. Try filtering in Excel

### Intermediate:
1. Install Python pandas
2. Run advanced examples
3. Create custom filters
4. Export to different formats

### Advanced:
1. Modify scraper for other sites
2. Create automated monitoring system
3. Build analysis dashboard
4. Integrate with database

---

## 🚀 What's Next?

After successfully scraping:

1. **Analyze trends**
   - Which categories are most popular?
   - What's the average bid amount?
   - Which affiliates have most items?

2. **Monitor opportunities**
   - Set alerts for specific keywords
   - Track high-value items
   - Watch closing times

3. **Automate workflows**
   - Schedule regular scrapes
   - Auto-filter results
   - Email alerts for items of interest

4. **Share insights**
   - Create visualizations
   - Generate reports
   - Present findings

---

## ✅ Final Checklist

Before running your first scrape:

- [ ] Python 3.7+ installed
- [ ] Dependencies installed (requests, beautifulsoup4)
- [ ] Tested with `python --version` or `python3 --version`
- [ ] Read QUICKSTART.md
- [ ] Decided on delay setting (1.0 recommended)
- [ ] Have disk space (CSV can be 50-100MB)
- [ ] Internet connection stable
- [ ] Ready to wait 30-45 minutes
- [ ] Know how to open CSV files

---

**Good luck with your scraping!** 🎉

For questions or issues, check:
1. README.md - Full documentation
2. QUICKSTART.md - Quick setup guide
3. kbid_scraper.log - Execution logs
4. advanced_examples.py - Usage examples
