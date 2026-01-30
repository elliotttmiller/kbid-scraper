#!/usr/bin/env python3
"""
Quick Start Demo - Auction Profit Analyzer

This script demonstrates how to use the auction analyzer
with example configurations and use cases.
"""

import os
from auction_profit_analyzer import (
    AuctionAnalyzer,
    AuctionDataParser,
    GeminiMarketResearcher,
    ProfitCalculator
)


def demo_basic_analysis():
    """Basic analysis of auction file"""
    
    print("="*70)
    print("DEMO 1: Basic Analysis")
    print("="*70)
    
    api_key = os.getenv('GOOGLE_API_KEY')
    if not api_key:
        print("❌ Set GOOGLE_API_KEY environment variable first!")
        return
    
    analyzer = AuctionAnalyzer(api_key)
    
    # Analyze first 5 items
    analyses = analyzer.analyze_auction_file(
        csv_filepath='/mnt/user-data/uploads/test_kbid_auction_1.csv',
        output_filepath='/mnt/user-data/outputs/demo_basic_results',
        max_items=5,
        min_opportunity_score=0  # Show all items
    )
    
    analyzer.print_summary(analyses)


def demo_filter_strong_buys():
    """Filter for only strong buy opportunities"""
    
    print("\n" + "="*70)
    print("DEMO 2: Filter for Strong Buy Opportunities Only")
    print("="*70)
    
    api_key = os.getenv('GOOGLE_API_KEY')
    if not api_key:
        print("❌ Set GOOGLE_API_KEY environment variable first!")
        return
    
    analyzer = AuctionAnalyzer(api_key)
    
    # Analyze more items, filter for high scores
    analyses = analyzer.analyze_auction_file(
        csv_filepath='/mnt/user-data/uploads/test_kbid_auction_1.csv',
        output_filepath='/mnt/user-data/outputs/demo_strong_buys',
        max_items=20,
        min_opportunity_score=60  # Only high-opportunity items
    )
    
    strong_buys = [a for a in analyses if a.recommendation == "STRONG BUY"]
    
    print(f"\n🎯 Found {len(strong_buys)} STRONG BUY opportunities")
    
    for analysis in strong_buys:
        print(f"\n{'='*70}")
        print(f"Lot #{analysis.item.lot_number}")
        print(f"{analysis.item.short_description[:100]}...")
        print(f"\n💰 Financial Analysis:")
        print(f"  Current Bid: ${analysis.item.current_bid:.2f}")
        print(f"  Est. Final Price: ${analysis.estimated_final_price:.2f}")
        print(f"  Expected Sell Price: ${analysis.expected_sell_price:.2f}")
        print(f"  Net Profit: ${analysis.net_profit:.2f}")
        print(f"  ROI: {analysis.roi:.1f}%")
        print(f"  Profit Margin: {analysis.profit_margin:.1f}%")
        print(f"\n📊 Scores:")
        print(f"  Opportunity: {analysis.opportunity_score:.1f}/100")
        print(f"  Risk: {analysis.risk_score}/10")
        print(f"  Demand: {analysis.market_research.demand_score}/10")
        print(f"  Liquidity: {analysis.market_research.liquidity_score}/10")
        print(f"\n💡 Reasoning: {analysis.reasoning}")
        print(f"🔗 URL: {analysis.item.item_url}")


def demo_category_analysis():
    """Analyze specific category"""
    
    print("\n" + "="*70)
    print("DEMO 3: Category-Specific Analysis")
    print("="*70)
    
    # Parse data
    items = AuctionDataParser.parse_csv('/mnt/user-data/uploads/test_kbid_auction_1.csv')
    
    # Group by category
    by_category = {}
    for item in items:
        cat = item.category
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(item)
    
    print(f"\n📦 Items by Category:")
    for category, items_list in sorted(by_category.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"  {category}: {len(items_list)} items")
    
    print("\nYou can filter your CSV by category before analysis for specialized research!")


def demo_custom_scoring():
    """Show how to customize scoring parameters"""
    
    print("\n" + "="*70)
    print("DEMO 4: Understanding Scoring")
    print("="*70)
    
    print("""
    The opportunity score (0-100) is calculated from:
    
    1. Net Profit (0-40 points):
       - >$200 = 40 points
       - >$100 = 30 points
       - >$50 = 20 points
       - >$25 = 10 points
    
    2. ROI (0-30 points):
       - >100% = 30 points
       - >75% = 25 points
       - >50% = 20 points
       - >25% = 10 points
    
    3. Demand Score (0-20 points):
       - Demand score × 2
    
    4. Liquidity (0-10 points):
       - Liquidity score (1-10)
    
    5. Risk Penalty:
       - Risk score × 2 (subtracted)
    
    Example:
    - Item with $150 profit, 80% ROI, 8/10 demand, 7/10 liquidity, 3/10 risk
    - Score = 30 + 25 + 16 + 7 - 6 = 72 (STRONG BUY)
    
    You can customize these weights in ProfitCalculator._calculate_opportunity_score()
    """)


def demo_profit_breakdown():
    """Show detailed profit calculation breakdown"""
    
    print("\n" + "="*70)
    print("DEMO 5: Profit Calculation Breakdown")
    print("="*70)
    
    print("""
    For each item, we calculate:
    
    COSTS:
    ------
    1. Purchase Price (Estimated Final Bid)
       - Current bid × 1.3 (assumes 30% increase)
       - Adjustable multiplier
    
    2. Shipping
       - 5% of item value (conservative estimate)
       - Can be customized per category
    
    3. Platform Fees (eBay default)
       - Final Value Fee: 12.95%
       - Payment Processing: 4.25%
       - Total: ~17.2% of selling price
    
    REVENUE:
    --------
    4. Expected Sell Price
       - Based on market research (used/retail avg)
       - Adjusted for condition:
         * New: 85% of retail
         * Refurbished: 75% of retail
         * Used: 100% of used avg
         * Damaged: 65% of used avg
       - Weighted with eBay sold data if available
       - Adjusted for market trend
    
    PROFIT:
    -------
    Net Profit = Expected Sell - (Purchase + Shipping + Fees)
    ROI = (Net Profit / Total Cost) × 100
    Margin = (Net Profit / Expected Sell) × 100
    
    EV+ = Net Profit > 0 AND Margin > 15%
    """)


def demo_risk_factors():
    """Explain risk scoring"""
    
    print("\n" + "="*70)
    print("DEMO 6: Risk Assessment Factors")
    print("="*70)
    
    print("""
    Risk Score (1-10, 10 = highest risk):
    
    1. Research Confidence
       - Low confidence from Gemini = higher risk
       - Points: (10 - confidence_score)
    
    2. Liquidity
       - How quickly item sells
       - Points: (10 - liquidity_score)
    
    3. Demand
       - Market demand level
       - Points: (10 - demand_score)
    
    4. Condition
       - Damaged: +15 points
       - Unknown: +10 points
       - Used: +5 points
       - New: 0 points
    
    5. Profit Margin
       - <10%: +15 points
       - <20%: +10 points
       - <30%: +5 points
    
    6. Market Trend
       - Decreasing: +10 points
       - Stable/Increasing: 0 points
    
    Total normalized to 1-10 scale.
    
    Risk Interpretation:
    - 1-3: Low risk (strong buy territory)
    - 4-6: Medium risk (acceptable for most)
    - 7-8: High risk (experienced only)
    - 9-10: Very high risk (avoid unless special circumstances)
    """)


if __name__ == "__main__":
    print("""
    ╔════════════════════════════════════════════════════════════════╗
    ║                                                                ║
    ║           AUCTION PROFIT ANALYZER - DEMO SUITE                 ║
    ║                                                                ║
    ║         Real-time Market Research & EV+ Identification         ║
    ║                                                                ║
    ╚════════════════════════════════════════════════════════════════╝
    """)
    
    print("\nAvailable Demos:")
    print("  1. Basic Analysis (5 items)")
    print("  2. Filter Strong Buys (20 items, high scores only)")
    print("  3. Category Analysis")
    print("  4. Scoring System Explanation")
    print("  5. Profit Calculation Breakdown")
    print("  6. Risk Assessment Factors")
    
    choice = input("\nSelect demo (1-6, or 'all'): ").strip()
    
    if choice == '1':
        demo_basic_analysis()
    elif choice == '2':
        demo_filter_strong_buys()
    elif choice == '3':
        demo_category_analysis()
    elif choice == '4':
        demo_custom_scoring()
    elif choice == '5':
        demo_profit_breakdown()
    elif choice == '6':
        demo_risk_factors()
    elif choice.lower() == 'all':
        demo_basic_analysis()
        demo_filter_strong_buys()
        demo_category_analysis()
        demo_custom_scoring()
        demo_profit_breakdown()
        demo_risk_factors()
    else:
        print("Invalid choice!")
