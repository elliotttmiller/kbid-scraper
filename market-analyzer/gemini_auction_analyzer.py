#!/usr/bin/env python3
"""
Gemini-Powered Auction Market Analyzer
Uses Google Gemini AI for intelligent market research and profit analysis
"""

import os
import sys
import json
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import re
from dataclasses import dataclass, asdict
import google.generativeai as genai
from concurrent.futures import ThreadPoolExecutor
import time


# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    """Configuration settings"""
    
    # Google AI API
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = "gemini-2.5-flash"
    
    # Cost parameters (K-Bid auction)
    BUYERS_PREMIUM_RATE = 0.18  # 18% buyer's premium
    SALES_TAX_RATE = 0.0725     # 7.25% Minnesota sales tax
    
    # Resale platform fees (eBay default)
    EBAY_FINAL_VALUE_FEE = 0.1350    # 13.5%
    EBAY_PAYMENT_FEE = 0.0425         # 4.25%
    EBAY_INSERTION_FEE = 0.35
    
    # Time costs
    HOURLY_RATE = 15.00  # Value of your time
    PHOTO_TIME_HOURS = 0.25  # 15 minutes
    LISTING_TIME_HOURS = 0.50  # 30 minutes
    
    # Storage and misc
    MONTHLY_STORAGE_COST = 5.00
    RETURN_RATE = 0.10  # 10% of items get returned
    
    # Thresholds
    MIN_CONFIDENCE_SCORE = 0.50
    MIN_OPPORTUNITY_SCORE = 60.0
    HIGH_OPPORTUNITY_SCORE = 75.0


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class ProductAnalysis:
    """AI-extracted product information"""
    brand: Optional[str]
    model: str
    category: str
    subcategory: Optional[str]
    condition: str
    condition_score: int  # 0-100
    key_features: List[str]
    damage_notes: str
    quantity: int
    is_lot: bool
    extracted_specs: Dict


@dataclass
class MarketResearch:
    """Market pricing data from Gemini"""
    median_price: float
    price_range_low: float
    price_range_high: float
    comparable_sales_count: int
    confidence_level: str  # "high", "medium", "low"
    confidence_score: float  # 0-1
    market_trend: str  # "stable", "rising", "falling"
    demand_level: str  # "high", "medium", "low"
    competition_level: str
    sell_through_rate: str
    avg_days_to_sell: int
    platform_recommendations: List[str]
    pricing_notes: str
    market_data_sources: List[str]


@dataclass
class ProfitAnalysis:
    """Profit and EV calculations"""
    estimated_acquisition_cost: float
    total_fixed_costs: float
    expected_sell_price: float
    expected_gross_profit: float
    expected_net_profit: float
    expected_roi_percent: float
    break_even_price: float
    best_case_profit: float
    worst_case_profit: float
    expected_value: float
    risk_score: float
    opportunity_score: float
    recommendation: str


# ============================================================================
# GEMINI AI MARKET RESEARCHER
# ============================================================================

class GeminiMarketResearcher:
    """Use Gemini AI for intelligent market research"""
    
    def __init__(self, api_key: str = None):
        """Initialize Gemini AI"""
        self.api_key = api_key or Config.GEMINI_API_KEY
        
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")
        
        # Configure Gemini
        genai.configure(api_key=self.api_key)
        
        # Initialize model
        self.model = genai.GenerativeModel(
            model_name=Config.GEMINI_MODEL,
            generation_config={
                "temperature": 0.3,  # Lower for more factual responses
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 2048,
            }
        )
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 0.5  # 2 requests per second max
    
    async def analyze_product(self, title: str, description: str, category: str) -> ProductAnalysis:
        """Use Gemini to extract structured product information"""
        
        prompt = f"""Analyze this auction listing and extract structured product information.

LISTING TITLE: {title}

DESCRIPTION: {description}

CATEGORY: {category}

Please analyze and provide:
1. Brand name (if identifiable)
2. Product model/name
3. Specific product category and subcategory
4. Condition assessment (New, Like New, Good, Fair, Poor, Parts)
5. Condition score (0-100, where 100=perfect new condition)
6. Key features or specifications
7. Any damage or defect notes
8. Quantity (how many items, is it a lot?)
9. Important specifications (size, capacity, etc.)

Return ONLY a valid JSON object with this exact structure:
{{
    "brand": "Brand Name or null",
    "model": "Product Model/Name",
    "category": "Specific Category",
    "subcategory": "Subcategory or null",
    "condition": "Condition Grade",
    "condition_score": 85,
    "key_features": ["feature1", "feature2"],
    "damage_notes": "Description of any damage",
    "quantity": 1,
    "is_lot": false,
    "extracted_specs": {{"spec_name": "value"}}
}}"""

        result = await self._call_gemini(prompt)
        
        try:
            # Parse JSON response
            data = json.loads(result)
            
            return ProductAnalysis(
                brand=data.get("brand"),
                model=data.get("model", title[:100]),
                category=data.get("category", category),
                subcategory=data.get("subcategory"),
                condition=data.get("condition", "Good"),
                condition_score=data.get("condition_score", 80),
                key_features=data.get("key_features", []),
                damage_notes=data.get("damage_notes", ""),
                quantity=data.get("quantity", 1),
                is_lot=data.get("is_lot", False),
                extracted_specs=data.get("extracted_specs", {})
            )
        
        except json.JSONDecodeError as e:
            print(f"Failed to parse Gemini response: {e}")
            print(f"Response was: {result[:200]}")
            
            # Return basic fallback
            return ProductAnalysis(
                brand=None,
                model=title[:100],
                category=category,
                subcategory=None,
                condition="Unknown",
                condition_score=70,
                key_features=[],
                damage_notes="",
                quantity=1,
                is_lot="LOT OF" in title.upper(),
                extracted_specs={}
            )
    
    async def research_market_price(self, product: ProductAnalysis) -> MarketResearch:
        """Use Gemini to research market prices and trends"""
        
        # Build comprehensive product description
        product_desc = f"{product.brand} {product.model}" if product.brand else product.model
        
        prompt = f"""As an expert resale market analyst, research current market prices and trends for this product:

PRODUCT: {product_desc}
CATEGORY: {product.category}
CONDITION: {product.condition} (Score: {product.condition_score}/100)
KEY FEATURES: {', '.join(product.key_features[:5])}
DAMAGE/NOTES: {product.damage_notes}
QUANTITY: {product.quantity}

Based on your knowledge of resale markets (eBay, Facebook Marketplace, Mercari, etc.), provide a comprehensive market analysis.

Consider:
1. Recent sold prices on eBay (last 30-90 days)
2. Current Amazon pricing (new and used)
3. Facebook Marketplace local pricing
4. Mercari and other platforms
5. Seasonal demand patterns
6. Current market trends
7. Competition level
8. How quickly items like this typically sell

Return ONLY a valid JSON object:
{{
    "median_price": 150.00,
    "price_range_low": 100.00,
    "price_range_high": 200.00,
    "comparable_sales_count": 25,
    "confidence_level": "high",
    "confidence_score": 0.85,
    "market_trend": "stable",
    "demand_level": "medium",
    "competition_level": "medium",
    "sell_through_rate": "70%",
    "avg_days_to_sell": 21,
    "platform_recommendations": ["eBay", "Facebook Marketplace"],
    "pricing_notes": "Brief analysis of pricing factors",
    "market_data_sources": ["eBay sold listings", "Amazon"]
}}

Be realistic and conservative in your estimates. Adjust prices based on the condition score provided.
"""

        result = await self._call_gemini(prompt)
        
        try:
            data = json.loads(result)
            
            return MarketResearch(
                median_price=data.get("median_price", 0),
                price_range_low=data.get("price_range_low", 0),
                price_range_high=data.get("price_range_high", 0),
                comparable_sales_count=data.get("comparable_sales_count", 0),
                confidence_level=data.get("confidence_level", "low"),
                confidence_score=data.get("confidence_score", 0.5),
                market_trend=data.get("market_trend", "stable"),
                demand_level=data.get("demand_level", "medium"),
                competition_level=data.get("competition_level", "medium"),
                sell_through_rate=data.get("sell_through_rate", "50%"),
                avg_days_to_sell=data.get("avg_days_to_sell", 30),
                platform_recommendations=data.get("platform_recommendations", ["eBay"]),
                pricing_notes=data.get("pricing_notes", ""),
                market_data_sources=data.get("market_data_sources", ["AI Knowledge Base"])
            )
        
        except json.JSONDecodeError as e:
            print(f"Failed to parse market research: {e}")
            
            # Return low-confidence fallback
            return MarketResearch(
                median_price=0,
                price_range_low=0,
                price_range_high=0,
                comparable_sales_count=0,
                confidence_level="low",
                confidence_score=0.3,
                market_trend="unknown",
                demand_level="unknown",
                competition_level="unknown",
                sell_through_rate="unknown",
                avg_days_to_sell=45,
                platform_recommendations=["eBay"],
                pricing_notes="Insufficient data for confident estimate",
                market_data_sources=[]
            )
    
    async def _call_gemini(self, prompt: str) -> str:
        """Make API call to Gemini with rate limiting"""
        
        # Rate limiting
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            await asyncio.sleep(self.min_request_interval - elapsed)
        
        try:
            # Generate content
            response = await asyncio.to_thread(
                self.model.generate_content,
                prompt
            )
            
            self.last_request_time = time.time()
            
            return response.text
        
        except Exception as e:
            print(f"Gemini API error: {e}")
            # Return empty JSON for graceful degradation
            return "{}"


# ============================================================================
# COST CALCULATOR
# ============================================================================

class CostCalculator:
    """Calculate all costs for auction items"""
    
    @staticmethod
    def calculate_acquisition_cost(current_bid: float) -> Dict:
        """Calculate total acquisition cost including fees and taxes"""
        
        buyers_premium = current_bid * Config.BUYERS_PREMIUM_RATE
        subtotal = current_bid + buyers_premium
        sales_tax = subtotal * Config.SALES_TAX_RATE
        total = current_bid + buyers_premium + sales_tax
        
        return {
            "hammer_price": current_bid,
            "buyers_premium": buyers_premium,
            "sales_tax": sales_tax,
            "total_acquisition": total
        }
    
    @staticmethod
    def estimate_shipping_cost(category: str, is_local: bool = True) -> float:
        """Estimate shipping/pickup costs"""
        
        if is_local:
            # Local pickup - gas + time
            return 15.00  # $10 gas + $5 time
        
        # Shipping estimates by category
        shipping_rates = {
            "Major Appliances": 75.00,
            "Electronics": 25.00,
            "Power Tools": 15.00,
            "Furniture": 100.00,
            "Clothing": 8.00,
            "Games": 10.00,
            "Outdoor": 20.00
        }
        
        # Match category
        for key, rate in shipping_rates.items():
            if key.lower() in category.lower():
                return rate
        
        return 15.00  # Default
    
    @staticmethod
    def calculate_overhead_costs() -> Dict:
        """Calculate time and storage overhead"""
        
        photo_cost = Config.PHOTO_TIME_HOURS * Config.HOURLY_RATE
        listing_cost = Config.LISTING_TIME_HOURS * Config.HOURLY_RATE
        storage_cost = Config.MONTHLY_STORAGE_COST
        
        return {
            "photography": photo_cost,
            "listing": listing_cost,
            "storage": storage_cost,
            "total_overhead": photo_cost + listing_cost + storage_cost
        }
    
    @staticmethod
    def calculate_platform_fees(sell_price: float) -> Dict:
        """Calculate eBay platform fees"""
        
        final_value_fee = sell_price * Config.EBAY_FINAL_VALUE_FEE
        payment_fee = sell_price * Config.EBAY_PAYMENT_FEE
        insertion_fee = Config.EBAY_INSERTION_FEE
        
        total = final_value_fee + payment_fee + insertion_fee
        
        return {
            "final_value_fee": final_value_fee,
            "payment_fee": payment_fee,
            "insertion_fee": insertion_fee,
            "total_platform_fees": total
        }
    
    @staticmethod
    def calculate_total_costs(
        current_bid: float,
        category: str,
        estimated_sell_price: float
    ) -> Dict:
        """Calculate all costs"""
        
        acquisition = CostCalculator.calculate_acquisition_cost(current_bid)
        shipping = CostCalculator.estimate_shipping_cost(category)
        overhead = CostCalculator.calculate_overhead_costs()
        platform_fees = CostCalculator.calculate_platform_fees(estimated_sell_price)
        
        # Return shipping risk (10% of items)
        return_shipping = shipping * Config.RETURN_RATE
        
        # Packaging
        packaging = 5.00
        
        fixed_costs = (
            acquisition["total_acquisition"] +
            shipping +
            packaging +
            overhead["total_overhead"]
        )
        
        variable_costs = platform_fees["total_platform_fees"] + return_shipping
        
        return {
            "acquisition": acquisition,
            "shipping": shipping,
            "packaging": packaging,
            "overhead": overhead,
            "platform_fees": platform_fees,
            "return_shipping": return_shipping,
            "fixed_costs": fixed_costs,
            "variable_costs": variable_costs,
            "total_costs": fixed_costs + variable_costs
        }


# ============================================================================
# PROFIT ANALYZER
# ============================================================================

class ProfitAnalyzer:
    """Calculate EV and profit potential"""
    
    @staticmethod
    def analyze_profit(
        current_bid: float,
        market_research: MarketResearch,
        product: ProductAnalysis,
        category: str
    ) -> ProfitAnalysis:
        """Comprehensive profit analysis"""
        
        # Calculate costs
        costs = CostCalculator.calculate_total_costs(
            current_bid,
            category,
            market_research.median_price
        )
        
        # Expected sell price (use median, adjusted for condition)
        condition_multiplier = product.condition_score / 85  # 85 = typical "good" condition
        expected_sell_price = market_research.median_price * condition_multiplier
        
        # Calculate profits for different scenarios
        best_case_sell = market_research.price_range_high * condition_multiplier
        worst_case_sell = market_research.price_range_low * condition_multiplier
        
        # Recalculate fees for each scenario
        expected_fees = CostCalculator.calculate_platform_fees(expected_sell_price)["total_platform_fees"]
        best_fees = CostCalculator.calculate_platform_fees(best_case_sell)["total_platform_fees"]
        worst_fees = CostCalculator.calculate_platform_fees(worst_case_sell)["total_platform_fees"]
        
        # Profits
        expected_gross = expected_sell_price - costs["fixed_costs"] - expected_fees
        best_profit = best_case_sell - costs["fixed_costs"] - best_fees
        worst_profit = worst_case_sell - costs["fixed_costs"] - worst_fees
        
        # Expected Value (weighted scenarios)
        ev = (
            best_profit * 0.20 +
            expected_gross * 0.60 +
            worst_profit * 0.20
        )
        
        # ROI
        roi = (expected_gross / costs["fixed_costs"] * 100) if costs["fixed_costs"] > 0 else 0
        
        # Break-even price (including all fees)
        break_even = costs["total_costs"] / (1 - Config.EBAY_FINAL_VALUE_FEE - Config.EBAY_PAYMENT_FEE)
        
        # Risk score (0-100, lower is better)
        downside_risk = abs(min(worst_profit, 0))
        upside_potential = max(best_profit, 0)
        risk_score = (downside_risk / (upside_potential + 1)) * 100
        
        # Opportunity score (0-100, higher is better)
        opportunity_score = ProfitAnalyzer._calculate_opportunity_score(
            roi,
            ev,
            market_research.confidence_score,
            risk_score,
            market_research.demand_level
        )
        
        # Recommendation
        recommendation = ProfitAnalyzer._generate_recommendation(
            opportunity_score,
            ev,
            roi,
            market_research.confidence_level
        )
        
        return ProfitAnalysis(
            estimated_acquisition_cost=costs["acquisition"]["total_acquisition"],
            total_fixed_costs=costs["fixed_costs"],
            expected_sell_price=expected_sell_price,
            expected_gross_profit=expected_gross,
            expected_net_profit=ev,
            expected_roi_percent=roi,
            break_even_price=break_even,
            best_case_profit=best_profit,
            worst_case_profit=worst_profit,
            expected_value=ev,
            risk_score=risk_score,
            opportunity_score=opportunity_score,
            recommendation=recommendation
        )
    
    @staticmethod
    def _calculate_opportunity_score(
        roi: float,
        ev: float,
        confidence: float,
        risk: float,
        demand: str
    ) -> float:
        """Calculate 0-100 opportunity score"""
        
        # ROI component (0-30 points)
        roi_score = min((roi / 50) * 30, 30)
        
        # EV component (0-25 points)
        ev_score = min((ev / 100) * 25, 25)
        
        # Confidence component (0-20 points)
        confidence_score = confidence * 20
        
        # Risk component (0-15 points, inverted)
        risk_score = max(0, 15 - (risk / 100 * 15))
        
        # Demand component (0-10 points)
        demand_scores = {"high": 10, "medium": 6, "low": 3, "unknown": 2}
        demand_score = demand_scores.get(demand.lower(), 2)
        
        total = roi_score + ev_score + confidence_score + risk_score + demand_score
        
        return min(total, 100)
    
    @staticmethod
    def _generate_recommendation(
        score: float,
        ev: float,
        roi: float,
        confidence: str
    ) -> str:
        """Generate action recommendation"""
        
        if score >= Config.HIGH_OPPORTUNITY_SCORE and ev > 50 and confidence in ["high", "medium"]:
            return "🔥 STRONG BUY - Excellent profit potential"
        elif score >= 65 and ev > 30:
            return "✅ BUY - Good opportunity"
        elif score >= 55:
            return "⚠️  CONSIDER - Moderate opportunity"
        elif score >= 45:
            return "⚡ MARGINAL - Low margin, high risk"
        else:
            return "❌ AVOID - Poor value or high risk"


# ============================================================================
# MAIN AUCTION ANALYZER
# ============================================================================

class GeminiAuctionAnalyzer:
    """Main analyzer orchestrating all components"""
    
    def __init__(self, gemini_api_key: str = None):
        """Initialize analyzer"""
        self.researcher = GeminiMarketResearcher(gemini_api_key)
        print("✓ Gemini AI initialized")
    
    async def analyze_item(self, row: Dict) -> Optional[Dict]:
        """Analyze a single auction item"""
        
        try:
            # Parse basic info
            lot_number = row.get("lot_number", "")
            title = row.get("item_title", "")
            description = row.get("short_description", "")
            category = row.get("category", "General")
            url = row.get("item_url", "")
            
            # Extract current bid (your CSV has bidder IDs, not prices)
            # For demo, estimate from next_required_bid or use placeholder
            next_bid_str = str(row.get("next_required_bid", "0"))
            if next_bid_str and next_bid_str != "N/A":
                try:
                    current_bid = float(next_bid_str.replace("$", "").replace(",", ""))
                except:
                    current_bid = 10.00  # Default placeholder
            else:
                current_bid = 10.00
            
            print(f"  Analyzing lot #{lot_number}: {title[:50]}...")
            
            # Step 1: AI product analysis
            product = await self.researcher.analyze_product(title, description, category)
            
            # Step 2: AI market research
            market = await self.researcher.research_market_price(product)
            
            # Skip if market confidence too low
            if market.confidence_score < Config.MIN_CONFIDENCE_SCORE:
                print(f"  ⚠️  Low confidence ({market.confidence_score:.2f}), skipping")
                return None
            
            # Step 3: Profit analysis
            profit = ProfitAnalyzer.analyze_profit(
                current_bid,
                market,
                product,
                category
            )
            
            # Skip if opportunity score too low
            if profit.opportunity_score < Config.MIN_OPPORTUNITY_SCORE:
                return None
            
            # Compile results
            result = {
                "lot_number": lot_number,
                "auction_id": row.get("auction_id", ""),
                "title": title,
                "category": category,
                "url": url,
                "current_bid": current_bid,
                
                # Product analysis
                "brand": product.brand,
                "model": product.model,
                "condition": product.condition,
                "condition_score": product.condition_score,
                "quantity": product.quantity,
                
                # Market research
                "estimated_market_value": market.median_price,
                "price_range": f"${market.price_range_low:.0f}-${market.price_range_high:.0f}",
                "market_confidence": market.confidence_level,
                "demand_level": market.demand_level,
                "avg_days_to_sell": market.avg_days_to_sell,
                "best_platforms": ", ".join(market.platform_recommendations),
                
                # Profit analysis
                "expected_sell_price": profit.expected_sell_price,
                "total_costs": profit.total_fixed_costs,
                "expected_profit": profit.expected_value,
                "expected_roi": profit.expected_roi_percent,
                "break_even_price": profit.break_even_price,
                "best_case_profit": profit.best_case_profit,
                "worst_case_profit": profit.worst_case_profit,
                
                # Scores
                "opportunity_score": profit.opportunity_score,
                "risk_score": profit.risk_score,
                "recommendation": profit.recommendation,
                
                # Additional notes
                "market_notes": market.pricing_notes,
                "analysis_timestamp": datetime.now().isoformat()
            }
            
            return result
        
        except Exception as e:
            print(f"  ❌ Error analyzing lot {row.get('lot_number', 'unknown')}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def analyze_batch(
        self,
        items: List[Dict],
        max_concurrent: int = 3,
        max_items: int = None
    ) -> List[Dict]:
        """Analyze multiple items with controlled concurrency"""
        
        if max_items:
            items = items[:max_items]
        
        print(f"\n🚀 Starting analysis of {len(items)} items...\n")
        
        # Process with concurrency limit
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def analyze_with_semaphore(item, index):
            async with semaphore:
                print(f"[{index+1}/{len(items)}]", end=" ")
                return await self.analyze_item(item)
        
        tasks = [analyze_with_semaphore(item, i) for i, item in enumerate(items)]
        results = await asyncio.gather(*tasks)
        
        # Filter successful analyses
        successful = [r for r in results if r is not None]
        
        # Sort by opportunity score
        successful.sort(key=lambda x: x["opportunity_score"], reverse=True)
        
        return successful
    
    def export_results(self, results: List[Dict], output_path: str):
        """Export results to CSV"""
        
        if not results:
            print("\n⚠️  No results to export")
            return
        
        df = pd.DataFrame(results)
        df.to_csv(output_path, index=False)
        print(f"\n✅ Results exported to: {output_path}")
    
    def print_summary(self, results: List[Dict]):
        """Print analysis summary"""
        
        if not results:
            print("\n❌ No profitable opportunities found")
            return
        
        print("\n" + "="*80)
        print("📊 AUCTION ANALYSIS SUMMARY")
        print("="*80)
        
        print(f"\n✅ Found {len(results)} profitable opportunities")
        
        # Statistics
        total_ev = sum(r["expected_profit"] for r in results)
        avg_roi = np.mean([r["expected_roi"] for r in results])
        avg_score = np.mean([r["opportunity_score"] for r in results])
        
        print(f"\n📈 Portfolio Statistics:")
        print(f"   Total Expected Value: ${total_ev:,.2f}")
        print(f"   Average ROI: {avg_roi:.1f}%")
        print(f"   Average Opportunity Score: {avg_score:.1f}/100")
        
        # Top opportunities
        print(f"\n🏆 TOP 10 OPPORTUNITIES:")
        print("-"*80)
        
        for i, item in enumerate(results[:10], 1):
            print(f"\n#{i} | Score: {item['opportunity_score']:.1f} | {item['recommendation']}")
            print(f"    Lot #{item['lot_number']}: {item['title'][:60]}")
            print(f"    Current Bid: ${item['current_bid']:.2f} → Est. Value: ${item['estimated_market_value']:.2f}")
            print(f"    Expected Profit: ${item['expected_profit']:.2f} ({item['expected_roi']:.1f}% ROI)")
            print(f"    Market: {item['market_confidence']} confidence, {item['demand_level']} demand")
            print(f"    Platforms: {item['best_platforms']}")
        
        print("\n" + "="*80)


# ============================================================================
# MAIN EXECUTION
# ============================================================================

async def main():
    """Main execution function"""
    
    print("\n" + "="*80)
    print("🤖 GEMINI-POWERED AUCTION ANALYZER")
    print("="*80 + "\n")
    
    # Check for API key
    if not Config.GEMINI_API_KEY:
        print("❌ Error: GEMINI_API_KEY environment variable not set")
        print("\nTo set it:")
        print("  export GEMINI_API_KEY='your-api-key-here'")
        print("\nGet your API key at: https://aistudio.google.com/app/apikey")
        return
    
    # Load CSV
    csv_path = "/mnt/user-data/uploads/test_kbid_auction_1.csv"
    
    try:
        df = pd.read_csv(csv_path)
        print(f"✓ Loaded {len(df)} auction items from CSV")
    except Exception as e:
        print(f"❌ Error loading CSV: {e}")
        return
    
    # Initialize analyzer
    analyzer = GeminiAuctionAnalyzer()
    
    # Analyze items (limit for demo - remove max_items for full analysis)
    items = df.to_dict('records')
    results = await analyzer.analyze_batch(
        items,
        max_concurrent=3,  # Process 3 at a time
        max_items=20  # Limit to 20 items for demo
    )
    
    # Export results
    output_path = "/mnt/user-data/outputs/gemini_auction_analysis.csv"
    analyzer.export_results(results, output_path)
    
    # Print summary
    analyzer.print_summary(results)
    
    # Export detailed JSON
    json_path = "/mnt/user-data/outputs/gemini_auction_analysis.json"
    with open(json_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n✅ Detailed JSON exported to: {json_path}")


if __name__ == "__main__":
    # Check if running in async context
    try:
        asyncio.run(main())
    except RuntimeError:
        # Already in async context
        import nest_asyncio
        nest_asyncio.apply()
        asyncio.get_event_loop().run_until_complete(main())
