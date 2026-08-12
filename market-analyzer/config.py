"""
Configuration file for Auction Profit Analyzer
Customize these values to match your business model and risk tolerance
"""

# ============================================================================
# MARKET RESEARCH SETTINGS
# ============================================================================

# Gemini API Configuration
GEMINI_MODEL = "gemini-2.5-flash"
RATE_LIMIT_RPM = 15  # Requests per minute (conservative)

# Research Quality Settings
MIN_RESEARCH_CONFIDENCE = 5  # Skip items with confidence below this (1-10)
PREFER_EBAY_SOLD_DATA = True  # Weight eBay sold data more heavily


# ============================================================================
# PROFIT CALCULATION SETTINGS
# ============================================================================

# Platform Fees (adjust based on your selling platform)
EBAY_FINAL_VALUE_FEE = 0.1295  # 12.95%
EBAY_PAYMENT_PROCESSING = 0.0425  # 4.25% (PayPal/Managed Payments)
EBAY_PROMOTED_LISTINGS = 0.00  # Optional: add promoted listings cost

AMAZON_REFERRAL_FEE = 0.15  # 15% (varies by category)
AMAZON_FBA_FEE = 0.00  # Add if using FBA

MERCARI_FEE = 0.10  # 10%
FACEBOOK_MARKETPLACE_FEE = 0.00  # Usually 0% for local

# Shipping Estimates
SHIPPING_MULTIPLIER = 0.05  # 5% of item value (conservative)
FLAT_SHIPPING_RATE = None  # Or set dollar amount like 15.00

# Auction Bid Estimation
FINAL_BID_MULTIPLIER = 1.3  # Assume bid increases 30% from current
# More conservative: 1.2, More aggressive: 1.5


# ============================================================================
# CONDITION ADJUSTMENTS
# ============================================================================

# Multiply expected sell price by these factors based on condition
CONDITION_MULTIPLIERS = {
    'New': 0.85,  # 85% of retail
    'Refurbished': 0.75,  # 75% of retail
    'Used': 1.0,  # 100% of used market price
    'Damaged': 0.65,  # 65% of used market price
    'Unknown': 0.80,  # Conservative 80%
}


# ============================================================================
# OPPORTUNITY SCORING WEIGHTS
# ============================================================================

# Net Profit Score (max 40 points)
PROFIT_THRESHOLDS = {
    200: 40,  # >$200 profit = 40 points
    100: 30,  # >$100 profit = 30 points
    50: 20,   # >$50 profit = 20 points
    25: 10,   # >$25 profit = 10 points
}

# ROI Score (max 30 points)
ROI_THRESHOLDS = {
    100: 30,  # >100% ROI = 30 points
    75: 25,   # >75% ROI = 25 points
    50: 20,   # >50% ROI = 20 points
    25: 10,   # >25% ROI = 10 points
}

# Market Factor Weights
DEMAND_WEIGHT = 2  # Multiply demand score by this
LIQUIDITY_WEIGHT = 1  # Add liquidity score directly
RISK_PENALTY_WEIGHT = 2  # Multiply risk score and subtract


# ============================================================================
# RISK SCORING WEIGHTS
# ============================================================================

# Condition Risk Points (added to risk score)
CONDITION_RISK = {
    'Damaged': 15,
    'Unknown': 10,
    'Used': 5,
    'Refurbished': 3,
    'New': 0,
}

# Profit Margin Risk Points
MARGIN_RISK_THRESHOLDS = {
    10: 15,  # <10% margin = 15 risk points
    20: 10,  # <20% margin = 10 risk points
    30: 5,   # <30% margin = 5 risk points
}

# Market Trend Risk
TREND_RISK = {
    'decreasing': 10,
    'stable': 0,
    'increasing': -5,  # Bonus for increasing demand
}


# ============================================================================
# RECOMMENDATION THRESHOLDS
# ============================================================================

# Strong Buy Requirements
STRONG_BUY_MIN_SCORE = 70
STRONG_BUY_MAX_RISK = 4
STRONG_BUY_REQUIRED_EV_POSITIVE = True

# Buy Requirements
BUY_MIN_SCORE = 50
BUY_MAX_RISK = 6
BUY_REQUIRED_EV_POSITIVE = True

# Maybe Requirements
MAYBE_MIN_SCORE = 30
MAYBE_REQUIRED_EV_POSITIVE = True

# EV+ Definition
MIN_PROFIT_MARGIN_FOR_EV = 15  # Minimum 15% profit margin


# ============================================================================
# FILTERING & OUTPUT SETTINGS
# ============================================================================

# Minimum Opportunity Score to Include in Results
MIN_OPPORTUNITY_SCORE = 20  # Filter out low-opportunity items

# Maximum Items to Analyze (None = all)
MAX_ITEMS_TO_ANALYZE = None  # Set to number for testing

# Output Settings
SAVE_JSON = True
SAVE_CSV = True
PRINT_DETAILED_LOGS = True  # Print each item as analyzed


# ============================================================================
# CATEGORY-SPECIFIC OVERRIDES (Advanced)
# ============================================================================

# You can override fees/shipping for specific categories
CATEGORY_OVERRIDES = {
    'Electronics': {
        'shipping_multiplier': 0.07,  # Electronics ship more expensive
        'condition_risk_bonus': 5,  # Higher risk for electronics
    },
    'Major Appliances': {
        'shipping_multiplier': 0.10,  # Heavy items
        'final_bid_multiplier': 1.2,  # Less bidding competition
    },
    'Furniture': {
        'shipping_multiplier': 0.15,  # Very expensive shipping
        'liquidity_penalty': 2,  # Harder to sell quickly
    },
    'Clothing, Shoes & Accessories': {
        'shipping_multiplier': 0.03,  # Cheap to ship
        'demand_bonus': 1,  # Usually good demand
    },
}


# ============================================================================
# MARKET TREND ADJUSTMENTS
# ============================================================================

# Seasonal Adjustments (optional, based on current date)
SEASONAL_MULTIPLIERS = {
    'Winter': {
        'Outdoor/Patio': 0.85,  # Lower demand in winter
        'Holiday/Seasonal': 1.15,  # Higher demand for holiday items
        'Exercise/Fitness': 1.1,  # New Year's resolutions
    },
    'Summer': {
        'Outdoor/Patio': 1.15,  # Higher summer demand
        'Holiday/Seasonal': 0.90,  # Lower off-season
    },
}

# Current season (auto-detect or set manually)
CURRENT_SEASON = 'Winter'  # Winter, Spring, Summer, Fall


# ============================================================================
# ADVANCED SETTINGS
# ============================================================================

# Research Cache (to avoid re-researching same items)
ENABLE_CACHE = False
CACHE_EXPIRY_HOURS = 24

# Parallel Processing (be careful with API rate limits)
ENABLE_PARALLEL = False
MAX_WORKERS = 3

# Backup Market Data Source
FALLBACK_TO_MANUAL_RESEARCH = False  # If Gemini fails, prompt for manual input

# Alerts & Notifications
ENABLE_ALERTS = False
ALERT_WEBHOOK_URL = None  # Slack/Discord webhook for strong buy alerts
ALERT_MIN_PROFIT = 100  # Only alert for profits above this


# ============================================================================
# VALIDATION
# ============================================================================

def validate_config():
    """Validate configuration values"""
    assert 0 <= EBAY_FINAL_VALUE_FEE <= 1, "Fee must be between 0 and 1"
    assert FINAL_BID_MULTIPLIER >= 1.0, "Bid multiplier must be >= 1.0"
    assert MIN_PROFIT_MARGIN_FOR_EV >= 0, "Minimum margin must be >= 0"
    print("✅ Configuration validated successfully")


if __name__ == "__main__":
    validate_config()
    print("\n📋 Current Configuration:")
    print(f"  Platform: eBay (fees: {EBAY_FINAL_VALUE_FEE*100:.2f}%)")
    print(f"  Shipping: {SHIPPING_MULTIPLIER*100:.0f}% of value")
    print(f"  Final bid estimate: {FINAL_BID_MULTIPLIER}x current")
    print(f"  Min EV+ margin: {MIN_PROFIT_MARGIN_FOR_EV}%")
    print(f"  Strong Buy score: {STRONG_BUY_MIN_SCORE}+")
    print(f"  Min opportunity score filter: {MIN_OPPORTUNITY_SCORE}")
