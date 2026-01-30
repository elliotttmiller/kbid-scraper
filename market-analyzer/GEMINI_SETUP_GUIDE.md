# Gemini-Powered Auction Analyzer - Complete Setup Guide

## Overview

This system uses Google's Gemini AI (Flash 2.0) to intelligently analyze auction listings and identify high-profit resale opportunities. Unlike traditional web scraping, Gemini provides:

- **Intelligent product extraction** - Understands context, brands, models, conditions
- **Market price estimation** - Leverages AI training on market data
- **Comprehensive analysis** - Considers demand, competition, seasonality
- **Fast processing** - Analyze 100+ items in minutes
- **Cost-effective** - Gemini Flash is extremely affordable

---

## Quick Start

### 1. Get Your Gemini API Key (Free!)

```bash
# Visit Google AI Studio
https://aistudio.google.com/app/apikey

# Click "Create API Key"
# Copy your key
```

**Pricing**: Gemini 2.0 Flash is **FREE** up to 1,500 requests/day!
- After free tier: $0.075 per 1M input tokens, $0.30 per 1M output tokens
- **Cost to analyze 1,000 items: ~$0.50-1.00**

### 2. Set Up Environment

```bash
# Set your API key
export GEMINI_API_KEY='your-api-key-here'

# Install required packages
pip install google-generativeai pandas numpy --break-system-packages

# Or create requirements.txt:
cat > requirements.txt << EOF
google-generativeai>=0.8.0
pandas>=2.0.0
numpy>=1.24.0
EOF

pip install -r requirements.txt --break-system-packages
```

### 3. Run the Analyzer

```bash
# Basic usage
python3 gemini_auction_analyzer.py

# Or in Python:
python3
>>> import asyncio
>>> from gemini_auction_analyzer import main
>>> asyncio.run(main())
```

---

## How It Works

### Architecture Flow

```
CSV Input → Gemini Product Analysis → Gemini Market Research → Cost Calculation → Profit Analysis → Ranked Results
```

### Step-by-Step Process

**For Each Auction Item:**

1. **Product Extraction (Gemini AI)**
   - Analyzes title + description
   - Extracts: brand, model, condition, specs, quantity
   - Assigns condition score (0-100)
   - Identifies damage/defects

2. **Market Research (Gemini AI)**
   - Estimates median resale price
   - Provides price range (low-high)
   - Assesses market demand & competition
   - Estimates days to sell
   - Recommends best platforms (eBay, Facebook, etc.)
   - Confidence scoring

3. **Cost Calculation**
   - Acquisition costs (bid + 18% premium + 7.25% tax)
   - Shipping/pickup costs
   - Platform fees (eBay: 13.5% FVF + 4.25% payment)
   - Time costs (photography, listing)
   - Storage & overhead

4. **Profit Analysis**
   - Expected Value (EV) calculation
   - ROI calculation
   - Best/worst case scenarios
   - Break-even price
   - Risk assessment

5. **Opportunity Scoring (0-100)**
   - ROI weight: 30%
   - Expected profit: 25%
   - Confidence: 20%
   - Risk (inverted): 15%
   - Demand: 10%

6. **Recommendation**
   - 🔥 STRONG BUY (75+ score)
   - ✅ BUY (65-74)
   - ⚠️ CONSIDER (55-64)
   - ⚡ MARGINAL (45-54)
   - ❌ AVOID (<45)

---

## Configuration Options

Edit the `Config` class in the script to customize:

```python
class Config:
    # Gemini settings
    GEMINI_MODEL = "gemini-2.0-flash-exp"  # Can use gemini-1.5-pro for better quality
    
    # Your auction platform fees
    BUYERS_PREMIUM_RATE = 0.18  # 18%
    SALES_TAX_RATE = 0.0725     # 7.25%
    
    # Resale platform (eBay default)
    EBAY_FINAL_VALUE_FEE = 0.1350
    EBAY_PAYMENT_FEE = 0.0425
    
    # Time value
    HOURLY_RATE = 15.00  # Your time value
    
    # Filters
    MIN_CONFIDENCE_SCORE = 0.50  # Skip items below 50% confidence
    MIN_OPPORTUNITY_SCORE = 60.0  # Only show items 60+ score
    HIGH_OPPORTUNITY_SCORE = 75.0  # "Strong buy" threshold
```

---

## Understanding the Output

### CSV Columns Explained

| Column | Description |
|--------|-------------|
| `lot_number` | Auction lot number |
| `title` | Item title |
| `brand` | Extracted brand (AI) |
| `model` | Product model/name |
| `condition` | Condition grade (New, Good, Fair, etc.) |
| `condition_score` | Condition 0-100 (100=perfect) |
| `current_bid` | Current auction bid |
| `estimated_market_value` | AI-estimated resale price |
| `expected_sell_price` | Adjusted for condition |
| `total_costs` | All costs (acquisition + fees + shipping) |
| `expected_profit` | Expected profit (EV) |
| `expected_roi` | Return on investment % |
| `opportunity_score` | 0-100 score (higher=better) |
| `recommendation` | Action recommendation |
| `market_confidence` | high/medium/low |
| `demand_level` | Market demand assessment |
| `best_platforms` | Recommended resale platforms |

### Example Output Row

```csv
lot_number,title,brand,condition,current_bid,estimated_market_value,expected_profit,expected_roi,opportunity_score,recommendation
1,Vissani 7.2 Refrigerator,Vissani,Fair,15.00,185.00,68.42,94.2,82.4,"🔥 STRONG BUY"
```

**Interpretation:**
- Currently bidding at $15
- AI estimates $185 resale value
- After all costs: $68 profit
- 94% ROI
- Score 82/100 = Strong Buy!

---

## Advanced Usage

### Analyze Specific Items

```python
import asyncio
import pandas as pd
from gemini_auction_analyzer import GeminiAuctionAnalyzer

async def analyze_specific_lots(lot_numbers: list):
    """Analyze only specific lot numbers"""
    
    # Load CSV
    df = pd.read_csv("/mnt/user-data/uploads/test_kbid_auction_1.csv")
    
    # Filter to specific lots
    df = df[df['lot_number'].isin(lot_numbers)]
    
    # Analyze
    analyzer = GeminiAuctionAnalyzer()
    items = df.to_dict('records')
    results = await analyzer.analyze_batch(items)
    
    return results

# Run it
results = asyncio.run(analyze_specific_lots([1, 5, 10, 25]))
```

### Batch Process Large Auctions

```python
async def analyze_large_auction(csv_path: str, batch_size: int = 50):
    """Process large auctions in batches"""
    
    df = pd.read_csv(csv_path)
    analyzer = GeminiAuctionAnalyzer()
    
    all_results = []
    
    # Process in batches
    for i in range(0, len(df), batch_size):
        batch = df.iloc[i:i+batch_size]
        items = batch.to_dict('records')
        
        print(f"\nProcessing batch {i//batch_size + 1}...")
        results = await analyzer.analyze_batch(items, max_concurrent=5)
        all_results.extend(results)
        
        # Save intermediate results
        pd.DataFrame(all_results).to_csv(
            f"results_batch_{i//batch_size + 1}.csv",
            index=False
        )
    
    return all_results

# Process 500 items in batches of 50
results = asyncio.run(analyze_large_auction("big_auction.csv", batch_size=50))
```

### Custom Filtering

```python
async def find_high_roi_items(min_roi: float = 100.0):
    """Find only items with >100% ROI"""
    
    df = pd.read_csv("/mnt/user-data/uploads/test_kbid_auction_1.csv")
    analyzer = GeminiAuctionAnalyzer()
    
    items = df.to_dict('records')
    results = await analyzer.analyze_batch(items)
    
    # Filter for high ROI
    high_roi = [r for r in results if r['expected_roi'] >= min_roi]
    
    print(f"\nFound {len(high_roi)} items with >{min_roi}% ROI")
    
    return high_roi
```

### Export to Different Formats

```python
def export_results(results: list, format: str = "csv"):
    """Export in various formats"""
    
    df = pd.DataFrame(results)
    
    if format == "csv":
        df.to_csv("results.csv", index=False)
    
    elif format == "excel":
        df.to_excel("results.xlsx", index=False)
    
    elif format == "json":
        import json
        with open("results.json", "w") as f:
            json.dump(results, f, indent=2, default=str)
    
    elif format == "html":
        # Create interactive HTML table
        html = df.to_html(index=False, classes='table table-striped')
        with open("results.html", "w") as f:
            f.write(f"""
            <html>
            <head>
                <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5/dist/css/bootstrap.min.css">
            </head>
            <body>
                <div class="container mt-5">
                    <h1>Auction Analysis Results</h1>
                    {html}
                </div>
            </body>
            </html>
            """)
```

---

## Optimization Tips

### 1. Improve Accuracy

```python
# Use the more powerful (but slower/pricier) model
Config.GEMINI_MODEL = "gemini-1.5-pro-002"

# Adjust temperature for more conservative estimates
generation_config = {
    "temperature": 0.1,  # Lower = more conservative
}
```

### 2. Speed Up Processing

```python
# Increase concurrent requests
results = await analyzer.analyze_batch(
    items,
    max_concurrent=10  # Process 10 at once (default: 3)
)
```

### 3. Reduce API Costs

```python
# Cache results to avoid re-analyzing same items
import pickle

def cache_results(results: list, filename: str):
    with open(filename, 'wb') as f:
        pickle.dump(results, f)

def load_cached_results(filename: str):
    try:
        with open(filename, 'rb') as f:
            return pickle.load(f)
    except FileNotFoundError:
        return None

# Usage
cached = load_cached_results('cache.pkl')
if cached:
    results = cached
else:
    results = await analyzer.analyze_batch(items)
    cache_results(results, 'cache.pkl')
```

### 4. Filter Before Analysis

```python
# Pre-filter to reduce API calls
df = pd.read_csv("auction.csv")

# Only analyze items in high-value categories
valuable_categories = ["Major Appliances", "Electronics", "Power Tools"]
df = df[df['category'].isin(valuable_categories)]

# Or filter by keywords
df = df[df['item_title'].str.contains('refrigerator|freezer|washer', case=False)]
```

---

## Troubleshooting

### Error: "API key not set"

```bash
# Make sure you exported the key
export GEMINI_API_KEY='your-key-here'

# Check it's set
echo $GEMINI_API_KEY

# Or set it in Python
import os
os.environ['GEMINI_API_KEY'] = 'your-key-here'
```

### Error: "Rate limit exceeded"

```python
# Gemini free tier: 15 requests/minute
# Solution: Reduce concurrency
results = await analyzer.analyze_batch(items, max_concurrent=1)

# Or add delays
self.min_request_interval = 1.0  # 1 second between requests
```

### Low Confidence Scores

Gemini might give low confidence if:
- Item description is vague
- Obscure/niche products
- Insufficient market data

**Solution**: Focus on common, name-brand items for best results.

### Parsing Errors

If Gemini returns invalid JSON:
- Check your prompts in the code
- Increase temperature slightly (0.3 → 0.4)
- Use gemini-1.5-pro for better JSON compliance

---

## Cost Analysis

### Gemini API Pricing (as of 2026)

**Gemini 2.0 Flash (Recommended)**
- Input: $0.075 per 1M tokens
- Output: $0.30 per 1M tokens
- **Free tier**: 1,500 requests/day

**Typical Usage:**
- Per item analysis: ~500 input tokens, ~300 output tokens
- **Cost per 1,000 items**: ~$0.40-0.60
- **Cost per month (100 items/day)**: ~$1-2

**Comparison to Traditional APIs:**
- eBay Finding API: Free (5,000/day)
- Amazon API: Free (with requirements)
- Keepa: $4 per 1,000 products
- **Gemini: $0.50 per 1,000 products**

**Total monthly cost (analyzing 3,000 items/month):**
- Gemini: $1.50
- eBay API: $0.00
- **Combined: ~$1.50/month**

---

## Best Practices

### 1. Start Small
- Test with 10-20 items first
- Validate results against known values
- Adjust confidence thresholds

### 2. Focus on High-Value Items
- Filter out items <$50 estimated value
- Prioritize categories you know well
- Use Gemini for items you're uncertain about

### 3. Combine with Manual Research
- Use Gemini for initial screening
- Manually verify top opportunities
- Check actual eBay sold listings for confirmation

### 4. Track Your Results
- Log actual outcomes vs. predictions
- Calculate real ROI achieved
- Adjust opportunity score weights based on data

### 5. Monitor Market Trends
- Re-analyze auctions weekly
- Watch for seasonal patterns
- Adjust for local market conditions

---

## Next Steps

1. **Run the analyzer** on your auction CSV
2. **Review top opportunities** (75+ score)
3. **Manually verify** top 5-10 items on eBay sold listings
4. **Place strategic bids** on validated opportunities
5. **Track results** and refine your approach

---

## Support Resources

- **Gemini API Docs**: https://ai.google.dev/gemini-api/docs
- **Pricing**: https://ai.google.dev/pricing
- **Get API Key**: https://aistudio.google.com/app/apikey
- **Community**: https://discuss.ai.google.dev/

---

## License & Disclaimer

This tool is for educational and research purposes. Always:
- Conduct your own due diligence
- Verify AI estimates with real market data
- Understand auction terms and conditions
- Never bid more than you can afford to lose

Market estimates are based on AI training data and may not reflect current real-time prices. Use as a screening tool, not a guarantee of profit.

---

**Happy hunting! 🎯**
