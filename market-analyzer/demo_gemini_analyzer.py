#!/usr/bin/env python3
"""
Quick Demo - Test Gemini Analyzer on Sample Items
Run this to validate your setup before processing full auction
"""

import os
import asyncio
import json
from gemini_auction_analyzer import (
    GeminiAuctionAnalyzer,
    Config
)


async def demo():
    """Run quick demo analysis"""
    
    print("\n" + "="*80)
    print("🎯 GEMINI AUCTION ANALYZER - QUICK DEMO")
    print("="*80 + "\n")
    
    # Check API key
    if not Config.GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY not set!")
        print("\nTo set it:")
        print("  export GEMINI_API_KEY='your-api-key-here'")
        print("\nGet your free API key at:")
        print("  https://aistudio.google.com/app/apikey\n")
        return
    
    print(f"✅ API Key configured: {Config.GEMINI_API_KEY[:20]}...")
    print(f"✅ Using model: {Config.GEMINI_MODEL}\n")
    
    # Sample auction items for testing
    sample_items = [
        {
            "lot_number": "DEMO-1",
            "auction_id": "DEMO",
            "item_title": "Vissani 7.2 cu. ft. Top Freezer Refrigerator",
            "short_description": "Fingerprint Resistant Stainless Steel Look (Minor Transit Damage, See Photos)",
            "category": "Major Appliances",
            "current_bid": "#107281",
            "next_required_bid": "15.00",
            "item_url": "https://example.com/item/1"
        },
        {
            "lot_number": "DEMO-2",
            "auction_id": "DEMO",
            "item_title": "DEWALT 20V MAX Cordless Drill/Driver Kit",
            "short_description": "DCD771C2 with 2 Batteries, Charger and Case - Like New Condition",
            "category": "Power Tools/Shop Equipment",
            "current_bid": "#12345",
            "next_required_bid": "45.00",
            "item_url": "https://example.com/item/2"
        },
        {
            "lot_number": "DEMO-3",
            "auction_id": "DEMO",
            "item_title": "Samsung 55-inch 4K Smart TV",
            "short_description": "UN55TU7000 Crystal UHD - Excellent condition, tested working",
            "category": "Electronics",
            "current_bid": "#99999",
            "next_required_bid": "150.00",
            "item_url": "https://example.com/item/3"
        }
    ]
    
    print(f"📦 Testing with {len(sample_items)} sample items:\n")
    for item in sample_items:
        print(f"  • {item['lot_number']}: {item['item_title']}")
    
    print(f"\n🚀 Starting analysis...\n")
    
    # Initialize analyzer
    try:
        analyzer = GeminiAuctionAnalyzer()
    except Exception as e:
        print(f"❌ Failed to initialize analyzer: {e}")
        return
    
    # Analyze items
    try:
        results = await analyzer.analyze_batch(
            sample_items,
            max_concurrent=2,
            max_items=None
        )
    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Display results
    if not results:
        print("\n⚠️  No profitable opportunities found in demo items")
        print("This might be due to:")
        print("  • Items being too damaged")
        print("  • Market values too low")
        print("  • Low confidence in estimates")
        return
    
    print("\n" + "="*80)
    print("✅ DEMO RESULTS")
    print("="*80 + "\n")
    
    for i, result in enumerate(results, 1):
        print(f"\n{'='*80}")
        print(f"ITEM #{i}: {result['title']}")
        print(f"{'='*80}")
        print(f"\n📊 SCORES:")
        print(f"   Opportunity Score: {result['opportunity_score']:.1f}/100")
        print(f"   {result['recommendation']}")
        
        print(f"\n💰 PRICING:")
        print(f"   Current Bid: ${result['current_bid']:.2f}")
        print(f"   Est. Market Value: ${result['estimated_market_value']:.2f}")
        print(f"   Expected Sell Price: ${result['expected_sell_price']:.2f}")
        print(f"   Price Range: {result['price_range']}")
        
        print(f"\n📈 PROFIT ANALYSIS:")
        print(f"   Total Costs: ${result['total_costs']:.2f}")
        print(f"   Expected Profit: ${result['expected_profit']:.2f}")
        print(f"   Expected ROI: {result['expected_roi']:.1f}%")
        print(f"   Break-Even Price: ${result['break_even_price']:.2f}")
        print(f"   Best Case: ${result['best_case_profit']:.2f}")
        print(f"   Worst Case: ${result['worst_case_profit']:.2f}")
        
        print(f"\n🔍 PRODUCT INFO:")
        print(f"   Brand: {result['brand'] or 'Unknown'}")
        print(f"   Condition: {result['condition']} ({result['condition_score']}/100)")
        print(f"   Quantity: {result['quantity']}")
        
        print(f"\n📊 MARKET ANALYSIS:")
        print(f"   Confidence: {result['market_confidence']}")
        print(f"   Demand: {result['demand_level']}")
        print(f"   Avg Days to Sell: {result['avg_days_to_sell']}")
        print(f"   Best Platforms: {result['best_platforms']}")
        if result['market_notes']:
            print(f"   Notes: {result['market_notes']}")
    
    # Save results
    output_file = "/mnt/user-data/outputs/demo_results.json"
    try:
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n\n✅ Full results saved to: {output_file}")
    except Exception as e:
        print(f"\n⚠️  Could not save results: {e}")
    
    print("\n" + "="*80)
    print("✅ DEMO COMPLETE!")
    print("="*80 + "\n")
    
    print("Next steps:")
    print("1. Review the results above")
    print("2. If satisfied, run the full analyzer on your auction CSV")
    print("3. Adjust Config settings in gemini_auction_analyzer.py as needed\n")


if __name__ == "__main__":
    try:
        asyncio.run(demo())
    except KeyboardInterrupt:
        print("\n\n⚠️  Demo cancelled by user")
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
