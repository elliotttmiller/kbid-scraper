# Auction Profit Analyzer - EV+ Opportunity Finder

A sophisticated real-time market research and profit analysis system for auction arbitrage. Uses Google Gemini AI to perform intelligent market research and identify high-profit resale opportunities.

## 🎯 Features

- **Real-time Market Research**: Uses Gemini API for live pricing data from eBay, Amazon, retail channels
- **Intelligent Profit Calculation**: Accounts for fees, shipping, condition, market trends
- **EV+ Identification**: Automatically flags Expected Value Positive opportunities
- **Risk Assessment**: Multi-factor risk scoring (1-10 scale)
- **Opportunity Ranking**: 0-100 score combining profit, ROI, demand, liquidity
- **Automated Recommendations**: "Strong Buy", "Buy", "Maybe", "Pass"
- **Comprehensive Reports**: JSON and CSV outputs with full analysis

## 📊 How It Works

### 1. Data Parsing
- Reads your auction scraping CSV
- Extracts item details, brands, models, condition
- Normalizes pricing data

### 2. Market Research (Gemini AI)
For each item, Gemini researches:
- Current retail prices (new)
- Used market prices
- Recent eBay sold listings
- Amazon pricing
- Market demand & trends
- Liquidity scores
- Comparable sales data

### 3. Profit Analysis
Calculates:
- Estimated final auction price
- Total costs (purchase + shipping + fees)
- Expected resale price (condition-adjusted)
- Net profit & margins
- ROI percentage
- Risk scores
- Opportunity scores

### 4. Ranking & Filtering
- Sorts by opportunity score
- Filters by minimum thresholds
- Generates actionable recommendations

## 🚀 Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Get Google API Key
1. Go to https://aistudio.google.com/apikey
2. Create a new API key
3. Set environment variable:

```bash
export GOOGLE_API_KEY='your-api-key-here'
```

Or add to your `.bashrc` / `.zshrc`:
```bash
echo "export GOOGLE_API_KEY='your-api-key-here'" >> ~/.bashrc
source ~/.bashrc
```

### 3. Prepare Your Data
Ensure your CSV has these columns:
- `lot_number`
- `item_title`
- `short_description`
- `current_bid`
- `category`
- `item_url`
- `image_url`
- `location`

## 💻 Usage

### Basic Usage
```bash
python auction_profit_analyzer.py
```

### Custom Configuration
Edit the configuration in `auction_profit_analyzer.py`:

```python
# Configuration
INPUT_FILE = 'path/to/your/auction_data.csv'
OUTPUT_FILE = 'path/to/output/results'
MAX_ITEMS = None  # Set to number or None for all items
MIN_OPPORTUNITY_SCORE = 20  # Only show items scoring >= 20
```

### Programmatic Usage
```python
from auction_profit_analyzer import AuctionAnalyzer

# Initialize
analyzer = AuctionAnalyzer(api_key='your-key')

# Analyze auction file
analyses = analyzer.analyze_auction_file(
    csv_filepath='auction_data.csv',
    output_filepath='results',
    max_items=50,  # Limit for testing
    min_opportunity_score=30  # Filter threshold
)

# Print summary
analyzer.print_summary(analyses)

# Access individual results
for analysis in analyses:
    if analysis.recommendation == "STRONG BUY":
        print(f"Lot {analysis.item.lot_number}")
        print(f"Profit: ${analysis.net_profit:.2f}")
        print(f"ROI: {analysis.roi:.1f}%")
```

## 📈 Understanding the Output

### Opportunity Score (0-100)
Combines multiple factors:
- **40 points**: Net profit amount
- **30 points**: ROI percentage
- **20 points**: Market demand
- **10 points**: Liquidity (how fast it sells)
- **Penalty**: Risk factors

### Risk Score (1-10)
Higher = more risk:
- Low research confidence
- Poor liquidity
- Low demand
- Damaged condition
- Thin profit margins
- Declining market trends

### Recommendations
- **STRONG BUY** (Score 70+, Low Risk): Best opportunities
- **BUY** (Score 50+, Medium Risk): Good opportunities
- **MAYBE** (Score 30+): For experienced flippers
- **PASS**: Not recommended

### Output Files

**JSON** (`results.json`):
```json
{
  "item": {
    "lot_number": "1",
    "description": "Vissani 7.2 cu. ft. Refrigerator...",
    "brand": "Vissani",
    "condition": "Damaged",
    "current_bid": 107281
  },
  "market_research": {
    "retail_avg": 349.99,
    "used_avg": 225.00,
    "ebay_sold_avg": 195.00,
    "demand_score": 7,
    "liquidity_score": 6,
    "trend": "stable"
  },
  "profit_analysis": {
    "net_profit": 45.50,
    "roi": 28.3,
    "opportunity_score": 62.5,
    "recommendation": "BUY"
  }
}
```

**CSV** (`results.csv`):
| Lot # | Description | Current Bid | Net Profit | ROI % | Score | Rec |
|-------|-------------|-------------|------------|-------|-------|-----|
| 1 | Vissani 7.2 cu. ft... | $107.28 | $45.50 | 28.3% | 62.5 | BUY |

## 🔧 Advanced Configuration

### Adjust Fee Structures
Edit in `ProfitCalculator` class:
```python
EBAY_FINAL_VALUE_FEE = 0.1295  # 12.95%
EBAY_PAYMENT_PROCESSING = 0.0425  # 4.25%
AMAZON_REFERRAL_FEE = 0.15  # 15%
SHIPPING_ESTIMATE_MULTIPLIER = 0.05  # 5% of value
```

### Change Gemini Model
```python
researcher = GeminiMarketResearcher(
    api_key, 
    model="gemini-2.0-flash-exp"  # Or other Gemini models
)
```

### Customize Risk Thresholds
Edit `_calculate_risk()` method to adjust risk weighting.

### Rate Limiting
Default: 15 requests/minute
```python
researcher._rate_limit(requests_per_minute=15)
```

## 📋 Example Workflow

1. **Scrape auctions** using your existing scraper → CSV file
2. **Run analyzer**: `python auction_profit_analyzer.py`
3. **Review results**: Check `results.json` and `results.csv`
4. **Filter for "STRONG BUY"** recommendations
5. **Bid strategically** on high-opportunity items
6. **Track performance** and refine scoring parameters

## ⚠️ Important Notes

### API Costs
- Gemini Flash is very affordable (~$0.075 per 1M input tokens)
- For 100 items at ~500 tokens each: ~$0.004
- Always monitor your usage

### Rate Limiting
- Default 15 requests/minute (conservative)
- Increase if your API quota allows
- Gemini Flash: 1000 RPM limit (paid tier)

### Data Quality
- More detailed item descriptions = better research
- Include brand/model when possible
- Clear condition notes improve accuracy

### Risk Management
- Start with small bids while learning
- Don't rely solely on automated recommendations
- Manual verification is recommended for high-value items
- Test with known items to calibrate scores

## 🎓 Tips for Success

1. **Specialize**: Focus on categories you know (appliances, electronics, etc.)
2. **Volume**: Analyze entire auctions to find hidden gems
3. **Timing**: Run analysis before auction closing to adjust bids
4. **Track Results**: Log actual profits to refine scoring
5. **Local Pickup**: Items with local pickup often have less competition
6. **Damaged Goods**: High-skill opportunity if you can repair
7. **Seasonal**: Adjust for seasonal demand (heaters in winter, etc.)

## 🔍 Troubleshooting

### "No JSON found in response"
- Gemini occasionally returns non-JSON
- Retry or check API status
- Consider adding retry logic

### Low Opportunity Scores
- Adjust `MIN_OPPORTUNITY_SCORE` threshold
- Check if market research is accurate
- Verify fee calculations match your platform

### Rate Limit Errors
- Reduce `requests_per_minute`
- Add longer delays between requests
- Upgrade API tier if needed

## 📚 Further Development

Potential enhancements:
- [ ] Integration with live auction APIs
- [ ] Image analysis for condition assessment
- [ ] Historical performance tracking
- [ ] Machine learning for better price predictions
- [ ] Multi-platform fee comparison (eBay vs Amazon vs Mercari)
- [ ] Automated bidding integration
- [ ] Telegram/Discord notifications for strong buys
- [ ] Portfolio optimization (best item mix)

## 📄 License

MIT License - Use freely for personal or commercial auction arbitrage.

## 🤝 Contributing

Found a way to improve profit calculations? Have better fee structures? Pull requests welcome!

---

**Disclaimer**: This tool provides analysis and recommendations based on market data. Actual results may vary. Always do your own due diligence before bidding on auction items.
