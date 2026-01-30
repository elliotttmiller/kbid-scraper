# Quick Reference Guide

## 🚀 Quick Start (3 Steps)

```bash
# 1. Install
pip install google-generativeai

# 2. Set API Key
export GOOGLE_API_KEY='your-key-here'

# 3. Run
python auction_profit_analyzer.py
```

## 📝 Common Commands

### Analyze Entire Auction
```python
python auction_profit_analyzer.py
# Outputs: results.json and results.csv
```

### Analyze First N Items (Testing)
```python
# Edit auction_profit_analyzer.py:
MAX_ITEMS = 10  # Analyze first 10 items
```

### Filter for Strong Buys Only
```python
# Edit auction_profit_analyzer.py:
MIN_OPPORTUNITY_SCORE = 60  # Only show high scores
```

### Run Demos
```bash
python demo.py
# Choose 1-6 or 'all'
```

## 🔧 Customization Cheat Sheet

### Change Platform Fees
Edit `config.py`:
```python
# For Mercari instead of eBay
EBAY_FINAL_VALUE_FEE = 0.10  # 10%
EBAY_PAYMENT_PROCESSING = 0.00
```

### Adjust Shipping Costs
```python
# Flat rate
SHIPPING_MULTIPLIER = 0.0
FLAT_SHIPPING_RATE = 15.00

# Or percentage
SHIPPING_MULTIPLIER = 0.08  # 8%
FLAT_SHIPPING_RATE = None
```

### Change Bid Estimation
```python
# Conservative (bids don't increase much)
FINAL_BID_MULTIPLIER = 1.15  # +15%

# Aggressive (competitive bidding)
FINAL_BID_MULTIPLIER = 1.5   # +50%
```

### Modify Scoring Weights
Edit `ProfitCalculator._calculate_opportunity_score()`:
```python
# Favor high ROI over raw profit
if roi > 100:
    score += 40  # Increase from 30
if net_profit > 50:
    score += 20  # Decrease from 30
```

## 📊 Output Format Reference

### JSON Structure
```json
{
  "item": {
    "lot_number": "1",
    "description": "...",
    "current_bid": 107.28
  },
  "market_research": {
    "retail_avg": 349.99,
    "used_avg": 225.00,
    "ebay_sold_avg": 195.00,
    "demand_score": 7,
    "liquidity_score": 6
  },
  "profit_analysis": {
    "net_profit": 45.50,
    "roi": 28.3,
    "opportunity_score": 62.5,
    "recommendation": "BUY"
  }
}
```

### CSV Columns
| Column | Description |
|--------|-------------|
| Lot # | Auction lot number |
| Description | Item description (truncated) |
| Current Bid | Current auction bid amount |
| Est. Final Price | Predicted final auction price |
| Expected Sell | Predicted resale price |
| Net Profit | Expected profit after all costs |
| ROI % | Return on investment percentage |
| Opportunity Score | 0-100 ranking score |
| Risk | Risk score 1-10 |
| Recommendation | STRONG BUY / BUY / MAYBE / PASS |

## 🎯 Filtering Strategies

### Find Best Opportunities
```python
# High profit, low risk
MIN_OPPORTUNITY_SCORE = 70
# Then filter JSON for risk_score <= 3
```

### Category-Specific Search
```python
# Parse CSV and filter by category first
items = [i for i in items if 'Appliances' in i.category]
# Then analyze
```

### Volume Play
```python
# Many small profits
MIN_OPPORTUNITY_SCORE = 30
# Filter for: net_profit > 20 and liquidity_score > 7
```

### Home Run Hunting
```python
# High-profit items only
MIN_OPPORTUNITY_SCORE = 50
# Filter JSON for: net_profit > 100
```

## 🔍 Interpreting Scores

### Opportunity Score
- **80-100**: Exceptional - Rare finds, act fast
- **60-79**: Excellent - Strong opportunities
- **40-59**: Good - Solid profits available
- **20-39**: Fair - Acceptable for volume
- **0-19**: Poor - Likely pass

### Risk Score
- **1-2**: Minimal risk - Blue chip items
- **3-4**: Low risk - Safe bets
- **5-6**: Medium risk - Standard auction risk
- **7-8**: High risk - Experienced only
- **9-10**: Very high - Speculative

### Demand Score
- **9-10**: Hot items - High competition
- **7-8**: Strong demand - Reliable market
- **5-6**: Moderate - Seasonal/niche
- **3-4**: Weak - Slow movers
- **1-2**: Poor - Hard to sell

### Liquidity Score
- **9-10**: Sells in days
- **7-8**: Sells in 1-2 weeks
- **5-6**: Sells in 1 month
- **3-4**: May take months
- **1-2**: Very slow sales

## 🛠️ Troubleshooting

### Error: "No JSON found in response"
```python
# Gemini returned non-JSON
# Solution: Add retry logic or use fallback
try:
    research = researcher.research_item(item)
except:
    # Skip or retry
    continue
```

### Error: Rate limit exceeded
```python
# In GeminiMarketResearcher.__init__():
self.rate_limit_rpm = 10  # Reduce from 15
```

### Low opportunity scores across board
```python
# Adjust thresholds in config.py:
PROFIT_THRESHOLDS = {
    100: 40,  # Lower from 200
    50: 30,   # Lower from 100
    # ...
}
```

### Gemini returns unrealistic prices
```python
# Add validation in _parse_research_response():
if data['used_price_avg'] > data['retail_price_avg'] * 1.5:
    # Flag as suspicious
    pass
```

## 💡 Pro Tips

### 1. Batch Processing
```python
# Process auctions in batches to manage API costs
for batch in batches_of_50(all_items):
    analyze_batch(batch)
    time.sleep(60)  # Rest between batches
```

### 2. Track Performance
```python
# Log actual vs predicted
actual_profit = 150
predicted_profit = 125
accuracy = actual_profit / predicted_profit
# Adjust multipliers based on accuracy
```

### 3. Specialize
```python
# Focus on 1-2 categories you know well
categories = ['Electronics', 'Power Tools']
items = [i for i in items if i.category in categories]
```

### 4. Local Pickup Advantage
```python
# Filter for local pickup items (less competition)
local_items = [i for i in items if 'local' in i.location.lower()]
```

### 5. Time-Based Strategy
```python
# Analyze early for planning, again before closing
early_analysis = analyze(items)  # 24h before
late_analysis = analyze(items)   # 1h before
# Compare price changes
```

## 📈 ROI Optimization

### Maximum Profit Per Item
- Filter: `opportunity_score > 70`
- Target: Net profit > $100
- Risk tolerance: <= 4

### Maximum Volume
- Filter: `opportunity_score > 30`
- Target: Many items > $20 profit
- Focus: High liquidity (>7)

### Balanced Portfolio
- Mix: 70% medium score (40-60)
- Add: 20% high score (60+)
- Speculate: 10% risky high-reward

## 🔐 Security Best Practices

### API Key Safety
```bash
# Never commit API keys
echo "GOOGLE_API_KEY='...'" >> ~/.bashrc
# Add to .gitignore
echo ".env" >> .gitignore
```

### Rate Limiting
```python
# Conservative default
RATE_LIMIT_RPM = 10  # Start low

# Monitor usage at
# https://aistudio.google.com/
```

## 📞 Quick Help

### Get API Key
https://aistudio.google.com/apikey

### Check API Usage
https://aistudio.google.com/

### Gemini Docs
https://ai.google.dev/docs

### Report Issues
Check if Gemini returned proper JSON format

---

**Remember**: Start small, validate results, then scale up!
