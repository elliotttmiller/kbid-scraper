#!/usr/bin/env python3
"""
Auction Profit Analyzer - Real-time Market Research & EV+ Identification
Uses Google Gemini API for intelligent market analysis and profit calculation
"""

import csv
import json
import re
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import google.generativeai as genai
import os


@dataclass
class AuctionItem:
    """Structured auction item data"""
    lot_number: str
    item_title: str
    short_description: str
    current_bid: float
    category: str
    item_url: str
    image_url: str
    location: str
    
    # Extracted/parsed fields
    brand: Optional[str] = None
    model: Optional[str] = None
    condition: Optional[str] = None
    key_features: List[str] = None
    
    def __post_init__(self):
        if self.key_features is None:
            self.key_features = []


@dataclass
class MarketResearch:
    """Market research results from Gemini"""
    retail_price_low: float
    retail_price_high: float
    retail_price_avg: float
    used_price_low: float
    used_price_high: float
    used_price_avg: float
    ebay_sold_avg: Optional[float]
    amazon_price: Optional[float]
    demand_score: int  # 1-10
    liquidity_score: int  # 1-10 (how fast it sells)
    market_trend: str  # "increasing", "stable", "decreasing"
    comparable_sales: List[Dict]
    research_confidence: int  # 1-10
    notes: str


@dataclass
class ProfitAnalysis:
    """Profit calculation and opportunity assessment"""
    item: AuctionItem
    market_research: MarketResearch
    
    # Cost calculations
    purchase_price: float  # current bid
    estimated_final_price: float  # predicted auction end price
    shipping_cost: float
    platform_fees: float  # eBay/Amazon fees
    total_cost: float
    
    # Revenue calculations
    expected_sell_price: float
    gross_revenue: float
    
    # Profit metrics
    net_profit: float
    profit_margin: float  # percentage
    roi: float  # percentage
    ev_positive: bool
    risk_score: int  # 1-10 (10 = highest risk)
    
    # Opportunity ranking
    opportunity_score: float  # 0-100
    recommendation: str  # "Strong Buy", "Buy", "Maybe", "Pass"
    reasoning: str


class AuctionDataParser:
    """Parse and clean auction CSV data"""
    
    @staticmethod
    def parse_csv(filepath: str) -> List[AuctionItem]:
        """Parse CSV file into structured AuctionItem objects"""
        items = []
        
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                try:
                    # Parse current bid (handle numeric bidder IDs)
                    current_bid = AuctionDataParser._parse_bid(row['current_bid'])
                    
                    # Skip items with no valid bid
                    if current_bid == 0:
                        continue
                    
                    item = AuctionItem(
                        lot_number=row['lot_number'],
                        item_title=row['item_title'],
                        short_description=row['short_description'],
                        current_bid=current_bid,
                        category=row['category'],
                        item_url=row['item_url'],
                        image_url=row['image_url'],
                        location=row['location']
                    )
                    
                    # Extract additional details
                    AuctionDataParser._extract_item_details(item)
                    
                    items.append(item)
                    
                except Exception as e:
                    print(f"Error parsing row {row.get('lot_number', 'unknown')}: {e}")
                    continue
        
        return items
    
    @staticmethod
    def _parse_bid(bid_str: str) -> float:
        """Extract numeric bid value from string"""
        if not bid_str or bid_str == 'N/A':
            return 0.0
        
        # Remove non-numeric characters except decimal point
        numeric = re.sub(r'[^\d.]', '', bid_str)
        
        try:
            return float(numeric) if numeric else 0.0
        except ValueError:
            return 0.0
    
    @staticmethod
    def _extract_item_details(item: AuctionItem):
        """Extract brand, model, condition from description"""
        desc = item.short_description.lower()
        
        # Extract condition
        if 'new' in desc or 'brand new' in desc:
            item.condition = 'New'
        elif 'damage' in desc or 'damaged' in desc:
            item.condition = 'Damaged'
        elif 'refurbished' in desc:
            item.condition = 'Refurbished'
        elif 'used' in desc:
            item.condition = 'Used'
        else:
            item.condition = 'Unknown'
        
        # Extract brand (common appliance brands)
        brands = ['vissani', 'newair', 'homcom', 'samsung', 'lg', 'whirlpool', 
                  'ge', 'frigidaire', 'kitchenaid', 'bosch', 'dyson']
        for brand in brands:
            if brand in desc:
                item.brand = brand.title()
                break
        
        # Extract key features
        features = []
        if 'cu. ft' in desc or 'cu ft' in desc:
            match = re.search(r'(\d+\.?\d*)\s*cu\.?\s*ft', desc)
            if match:
                features.append(f"{match.group(1)} cu. ft.")
        
        if 'stainless steel' in desc:
            features.append('Stainless Steel')
        
        item.key_features = features


class GeminiMarketResearcher:
    """Use Gemini API for intelligent market research"""
    
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        """Initialize Gemini API"""
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model)
        self.request_count = 0
        self.last_request_time = 0
    
    def research_item(self, item: AuctionItem) -> MarketResearch:
        """Perform comprehensive market research on an item"""
        
        # Rate limiting (be respectful to API)
        self._rate_limit()
        
        # Build research prompt
        prompt = self._build_research_prompt(item)
        
        try:
            response = self.model.generate_content(prompt)
            research = self._parse_research_response(response.text)
            return research
            
        except Exception as e:
            print(f"Error researching item {item.lot_number}: {e}")
            # Return conservative default research
            return self._get_default_research()
    
    def _rate_limit(self, requests_per_minute: int = 15):
        """Simple rate limiting"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < (60.0 / requests_per_minute):
            sleep_time = (60.0 / requests_per_minute) - time_since_last
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
        self.request_count += 1
    
    def _build_research_prompt(self, item: AuctionItem) -> str:
        """Build comprehensive market research prompt for Gemini"""
        
        prompt = f"""You are an expert market researcher and pricing analyst specializing in resale arbitrage and auction flipping.

Analyze this auction item and provide comprehensive market research for resale profit potential:

ITEM DETAILS:
- Description: {item.short_description}
- Brand: {item.brand or 'Unknown'}
- Condition: {item.condition}
- Category: {item.category}
- Current Bid: ${item.current_bid:.2f}
- Features: {', '.join(item.key_features) if item.key_features else 'None specified'}

RESEARCH REQUIRED:
1. Current retail prices (new) - provide low, high, and average
2. Used/refurbished market prices - provide low, high, and average
3. Recent eBay sold listings (last 30-90 days) - average sold price
4. Current Amazon pricing (if available)
5. Market demand assessment (1-10 scale)
6. Liquidity score - how quickly items sell (1-10 scale, 10=sells within days)
7. Market trend (increasing/stable/decreasing demand)
8. 3-5 comparable recent sales with prices
9. Research confidence level (1-10, based on data availability)
10. Special notes about condition, market factors, or risks

RESPOND IN STRICT JSON FORMAT:
{{
  "retail_price_low": 299.99,
  "retail_price_high": 399.99,
  "retail_price_avg": 349.99,
  "used_price_low": 150.00,
  "used_price_high": 250.00,
  "used_price_avg": 200.00,
  "ebay_sold_avg": 185.00,
  "amazon_price": 329.99,
  "demand_score": 7,
  "liquidity_score": 6,
  "market_trend": "stable",
  "comparable_sales": [
    {{"platform": "eBay", "price": 195.00, "condition": "Used", "date": "2025-01-15"}},
    {{"platform": "eBay", "price": 175.00, "condition": "Used - Minor Damage", "date": "2025-01-10"}},
    {{"platform": "Facebook Marketplace", "price": 200.00, "condition": "Like New", "date": "2025-01-08"}}
  ],
  "research_confidence": 8,
  "notes": "Strong market for this model. Damage may reduce value by 15-25%. Seasonal demand is moderate."
}}

Be realistic and conservative in pricing. Consider the condition carefully. If item is damaged, factor that into pricing.
"""
        return prompt
    
    def _parse_research_response(self, response_text: str) -> MarketResearch:
        """Parse Gemini's JSON response into MarketResearch object"""
        
        # Extract JSON from response (sometimes wrapped in markdown)
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON found in response")
        
        data = json.loads(json_match.group())
        
        return MarketResearch(
            retail_price_low=float(data.get('retail_price_low', 0)),
            retail_price_high=float(data.get('retail_price_high', 0)),
            retail_price_avg=float(data.get('retail_price_avg', 0)),
            used_price_low=float(data.get('used_price_low', 0)),
            used_price_high=float(data.get('used_price_high', 0)),
            used_price_avg=float(data.get('used_price_avg', 0)),
            ebay_sold_avg=float(data.get('ebay_sold_avg')) if data.get('ebay_sold_avg') else None,
            amazon_price=float(data.get('amazon_price')) if data.get('amazon_price') else None,
            demand_score=int(data.get('demand_score', 5)),
            liquidity_score=int(data.get('liquidity_score', 5)),
            market_trend=data.get('market_trend', 'stable'),
            comparable_sales=data.get('comparable_sales', []),
            research_confidence=int(data.get('research_confidence', 5)),
            notes=data.get('notes', '')
        )
    
    def _get_default_research(self) -> MarketResearch:
        """Return conservative default research when API fails"""
        return MarketResearch(
            retail_price_low=0,
            retail_price_high=0,
            retail_price_avg=0,
            used_price_low=0,
            used_price_high=0,
            used_price_avg=0,
            ebay_sold_avg=None,
            amazon_price=None,
            demand_score=5,
            liquidity_score=5,
            market_trend='unknown',
            comparable_sales=[],
            research_confidence=1,
            notes='API error - manual research required'
        )


class ProfitCalculator:
    """Calculate profit potential and opportunity scores"""
    
    # Fee structures (adjustable)
    EBAY_FINAL_VALUE_FEE = 0.1295  # 12.95%
    EBAY_PAYMENT_PROCESSING = 0.0425  # 4.25%
    AMAZON_REFERRAL_FEE = 0.15  # 15% (varies by category)
    SHIPPING_ESTIMATE_MULTIPLIER = 0.05  # 5% of item value
    
    @staticmethod
    def analyze_profit(item: AuctionItem, research: MarketResearch) -> ProfitAnalysis:
        """Comprehensive profit analysis"""
        
        # Estimate final auction price (usually 1.2-1.5x current bid)
        estimated_final = item.current_bid * 1.3
        
        # Calculate costs
        shipping = estimated_final * ProfitCalculator.SHIPPING_ESTIMATE_MULTIPLIER
        
        # Determine expected sell price based on condition and research
        expected_sell_price = ProfitCalculator._calculate_expected_sell_price(
            item, research
        )
        
        # Calculate platform fees (use eBay as default)
        platform_fees = expected_sell_price * (
            ProfitCalculator.EBAY_FINAL_VALUE_FEE + 
            ProfitCalculator.EBAY_PAYMENT_PROCESSING
        )
        
        total_cost = estimated_final + shipping
        gross_revenue = expected_sell_price
        net_profit = gross_revenue - total_cost - platform_fees
        
        profit_margin = (net_profit / gross_revenue * 100) if gross_revenue > 0 else 0
        roi = (net_profit / total_cost * 100) if total_cost > 0 else 0
        
        # Determine if EV+
        ev_positive = net_profit > 0 and profit_margin > 15  # At least 15% margin
        
        # Calculate risk score
        risk_score = ProfitCalculator._calculate_risk(item, research, profit_margin)
        
        # Calculate opportunity score
        opportunity_score = ProfitCalculator._calculate_opportunity_score(
            net_profit, roi, research, risk_score
        )
        
        # Generate recommendation
        recommendation, reasoning = ProfitCalculator._generate_recommendation(
            ev_positive, opportunity_score, net_profit, roi, risk_score, research
        )
        
        return ProfitAnalysis(
            item=item,
            market_research=research,
            purchase_price=item.current_bid,
            estimated_final_price=estimated_final,
            shipping_cost=shipping,
            platform_fees=platform_fees,
            total_cost=total_cost,
            expected_sell_price=expected_sell_price,
            gross_revenue=gross_revenue,
            net_profit=net_profit,
            profit_margin=profit_margin,
            roi=roi,
            ev_positive=ev_positive,
            risk_score=risk_score,
            opportunity_score=opportunity_score,
            recommendation=recommendation,
            reasoning=reasoning
        )
    
    @staticmethod
    def _calculate_expected_sell_price(item: AuctionItem, research: MarketResearch) -> float:
        """Calculate realistic expected sell price based on condition and market"""
        
        # Start with used average price
        base_price = research.used_price_avg if research.used_price_avg > 0 else research.retail_price_avg * 0.6
        
        # Adjust for condition
        if item.condition == 'New':
            multiplier = 0.85  # 85% of retail
            base_price = research.retail_price_avg * multiplier
        elif item.condition == 'Damaged':
            multiplier = 0.65  # 65% of used price
            base_price = base_price * multiplier
        elif item.condition == 'Refurbished':
            multiplier = 0.75  # 75% of retail
            base_price = research.retail_price_avg * multiplier
        
        # Use eBay sold average if available (most reliable)
        if research.ebay_sold_avg and research.ebay_sold_avg > 0:
            # Weight eBay data heavily
            base_price = (base_price * 0.3) + (research.ebay_sold_avg * 0.7)
        
        # Adjust for market trend
        if research.market_trend == 'decreasing':
            base_price *= 0.9  # 10% reduction
        elif research.market_trend == 'increasing':
            base_price *= 1.05  # 5% increase
        
        # Conservative adjustment for liquidity
        if research.liquidity_score < 5:
            base_price *= 0.95  # Harder to sell, price it lower
        
        return round(base_price, 2)
    
    @staticmethod
    def _calculate_risk(item: AuctionItem, research: MarketResearch, profit_margin: float) -> int:
        """Calculate risk score (1-10, 10=highest risk)"""
        
        risk = 0
        
        # Research confidence (low confidence = high risk)
        risk += (10 - research.research_confidence)
        
        # Liquidity risk
        risk += (10 - research.liquidity_score)
        
        # Demand risk
        risk += (10 - research.demand_score)
        
        # Condition risk
        if item.condition == 'Damaged':
            risk += 15
        elif item.condition == 'Unknown':
            risk += 10
        elif item.condition == 'Used':
            risk += 5
        
        # Profit margin risk (thin margins = higher risk)
        if profit_margin < 10:
            risk += 15
        elif profit_margin < 20:
            risk += 10
        elif profit_margin < 30:
            risk += 5
        
        # Market trend risk
        if research.market_trend == 'decreasing':
            risk += 10
        
        # Normalize to 1-10 scale
        risk_score = min(10, max(1, int(risk / 6)))
        
        return risk_score
    
    @staticmethod
    def _calculate_opportunity_score(
        net_profit: float, 
        roi: float, 
        research: MarketResearch, 
        risk_score: int
    ) -> float:
        """Calculate opportunity score (0-100)"""
        
        score = 0
        
        # Profit component (0-40 points)
        if net_profit > 200:
            score += 40
        elif net_profit > 100:
            score += 30
        elif net_profit > 50:
            score += 20
        elif net_profit > 25:
            score += 10
        
        # ROI component (0-30 points)
        if roi > 100:
            score += 30
        elif roi > 75:
            score += 25
        elif roi > 50:
            score += 20
        elif roi > 25:
            score += 10
        
        # Market factors (0-20 points)
        score += research.demand_score * 2
        
        # Liquidity bonus (0-10 points)
        score += research.liquidity_score
        
        # Risk penalty
        score -= (risk_score * 2)
        
        # Normalize to 0-100
        return max(0, min(100, score))
    
    @staticmethod
    def _generate_recommendation(
        ev_positive: bool,
        opportunity_score: float,
        net_profit: float,
        roi: float,
        risk_score: int,
        research: MarketResearch
    ) -> Tuple[str, str]:
        """Generate recommendation and reasoning"""
        
        if opportunity_score >= 70 and ev_positive and risk_score <= 4:
            recommendation = "STRONG BUY"
            reasoning = f"Excellent opportunity: High profit (${net_profit:.2f}), strong ROI ({roi:.1f}%), low risk, good market demand."
        
        elif opportunity_score >= 50 and ev_positive and risk_score <= 6:
            recommendation = "BUY"
            reasoning = f"Good opportunity: Solid profit (${net_profit:.2f}), decent ROI ({roi:.1f}%), acceptable risk."
        
        elif opportunity_score >= 30 and ev_positive:
            recommendation = "MAYBE"
            reasoning = f"Marginal opportunity: Modest profit (${net_profit:.2f}), ROI {roi:.1f}%. Risk score: {risk_score}/10. Consider if experienced."
        
        else:
            recommendation = "PASS"
            reasons = []
            if not ev_positive:
                reasons.append("not EV+")
            if risk_score >= 7:
                reasons.append(f"high risk ({risk_score}/10)")
            if net_profit < 20:
                reasons.append("low profit potential")
            if research.liquidity_score < 4:
                reasons.append("poor liquidity")
            
            reasoning = f"Not recommended: {', '.join(reasons)}."
        
        return recommendation, reasoning


class AuctionAnalyzer:
    """Main analyzer orchestrating the complete workflow"""
    
    def __init__(self, gemini_api_key: str):
        self.researcher = GeminiMarketResearcher(gemini_api_key)
        self.calculator = ProfitCalculator()
    
    def analyze_auction_file(
        self, 
        csv_filepath: str, 
        output_filepath: str = None,
        max_items: int = None,
        min_opportunity_score: float = 0
    ) -> List[ProfitAnalysis]:
        """Analyze entire auction CSV file"""
        
        print(f"📊 Parsing auction data from {csv_filepath}...")
        items = AuctionDataParser.parse_csv(csv_filepath)
        
        if max_items:
            items = items[:max_items]
        
        print(f"✅ Found {len(items)} valid items")
        print(f"🔍 Starting market research and profit analysis...\n")
        
        analyses = []
        
        for i, item in enumerate(items, 1):
            print(f"[{i}/{len(items)}] Analyzing Lot #{item.lot_number}: {item.short_description[:60]}...")
            
            # Research market
            research = self.researcher.research_item(item)
            
            # Calculate profit
            analysis = self.calculator.analyze_profit(item, research)
            
            # Filter by minimum opportunity score
            if analysis.opportunity_score >= min_opportunity_score:
                analyses.append(analysis)
                
                print(f"  ├─ Recommendation: {analysis.recommendation}")
                print(f"  ├─ Net Profit: ${analysis.net_profit:.2f}")
                print(f"  ├─ ROI: {analysis.roi:.1f}%")
                print(f"  ├─ Opportunity Score: {analysis.opportunity_score:.1f}/100")
                print(f"  └─ Risk: {analysis.risk_score}/10\n")
            else:
                print(f"  └─ Skipped (opportunity score too low)\n")
        
        # Sort by opportunity score
        analyses.sort(key=lambda x: x.opportunity_score, reverse=True)
        
        # Save results
        if output_filepath:
            self._save_results(analyses, output_filepath)
        
        return analyses
    
    def _save_results(self, analyses: List[ProfitAnalysis], filepath: str):
        """Save analysis results to JSON and CSV"""
        
        # JSON (full details)
        json_path = filepath.replace('.csv', '.json') if '.csv' in filepath else f"{filepath}.json"
        
        results = []
        for analysis in analyses:
            result = {
                'item': {
                    'lot_number': analysis.item.lot_number,
                    'description': analysis.item.short_description,
                    'brand': analysis.item.brand,
                    'condition': analysis.item.condition,
                    'category': analysis.item.category,
                    'url': analysis.item.item_url,
                    'current_bid': analysis.item.current_bid
                },
                'market_research': {
                    'retail_avg': analysis.market_research.retail_price_avg,
                    'used_avg': analysis.market_research.used_price_avg,
                    'ebay_sold_avg': analysis.market_research.ebay_sold_avg,
                    'demand_score': analysis.market_research.demand_score,
                    'liquidity_score': analysis.market_research.liquidity_score,
                    'trend': analysis.market_research.market_trend,
                    'confidence': analysis.market_research.research_confidence,
                    'notes': analysis.market_research.notes
                },
                'profit_analysis': {
                    'estimated_final_price': analysis.estimated_final_price,
                    'total_cost': analysis.total_cost,
                    'expected_sell_price': analysis.expected_sell_price,
                    'net_profit': analysis.net_profit,
                    'profit_margin': analysis.profit_margin,
                    'roi': analysis.roi,
                    'ev_positive': analysis.ev_positive,
                    'risk_score': analysis.risk_score,
                    'opportunity_score': analysis.opportunity_score,
                    'recommendation': analysis.recommendation,
                    'reasoning': analysis.reasoning
                }
            }
            results.append(result)
        
        with open(json_path, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n💾 Saved detailed results to {json_path}")
        
        # CSV (summary)
        csv_path = filepath if '.csv' in filepath else f"{filepath}.csv"
        
        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Lot #', 'Description', 'Brand', 'Condition', 'Current Bid',
                'Est. Final Price', 'Expected Sell', 'Net Profit', 'ROI %',
                'Opportunity Score', 'Risk', 'Recommendation', 'URL'
            ])
            
            for analysis in analyses:
                writer.writerow([
                    analysis.item.lot_number,
                    analysis.item.short_description[:80],
                    analysis.item.brand or 'Unknown',
                    analysis.item.condition,
                    f"${analysis.item.current_bid:.2f}",
                    f"${analysis.estimated_final_price:.2f}",
                    f"${analysis.expected_sell_price:.2f}",
                    f"${analysis.net_profit:.2f}",
                    f"{analysis.roi:.1f}%",
                    f"{analysis.opportunity_score:.1f}",
                    f"{analysis.risk_score}/10",
                    analysis.recommendation,
                    analysis.item.item_url
                ])
        
        print(f"💾 Saved summary to {csv_path}")
    
    def print_summary(self, analyses: List[ProfitAnalysis]):
        """Print summary statistics"""
        
        if not analyses:
            print("\n⚠️  No items met the criteria")
            return
        
        strong_buys = [a for a in analyses if a.recommendation == "STRONG BUY"]
        buys = [a for a in analyses if a.recommendation == "BUY"]
        maybes = [a for a in analyses if a.recommendation == "MAYBE"]
        
        total_potential_profit = sum(a.net_profit for a in analyses if a.ev_positive)
        avg_roi = sum(a.roi for a in analyses) / len(analyses)
        
        print("\n" + "="*70)
        print("📈 ANALYSIS SUMMARY")
        print("="*70)
        print(f"Total items analyzed: {len(analyses)}")
        print(f"\nRecommendations:")
        print(f"  🟢 STRONG BUY: {len(strong_buys)}")
        print(f"  🔵 BUY: {len(buys)}")
        print(f"  🟡 MAYBE: {len(maybes)}")
        print(f"\nFinancials:")
        print(f"  Total potential profit: ${total_potential_profit:.2f}")
        print(f"  Average ROI: {avg_roi:.1f}%")
        print("\nTop 5 Opportunities:")
        
        for i, analysis in enumerate(analyses[:5], 1):
            print(f"\n{i}. Lot #{analysis.item.lot_number} - {analysis.recommendation}")
            print(f"   {analysis.item.short_description[:70]}")
            print(f"   Net Profit: ${analysis.net_profit:.2f} | ROI: {analysis.roi:.1f}% | Score: {analysis.opportunity_score:.1f}")
            print(f"   {analysis.reasoning}")
        
        print("\n" + "="*70)


if __name__ == "__main__":
    import sys
    
    # Check for API key
    api_key = os.getenv('GOOGLE_API_KEY')
    
    if not api_key:
        print("❌ Error: GOOGLE_API_KEY environment variable not set")
        print("\nSet it with:")
        print("  export GOOGLE_API_KEY='your-api-key-here'")
        sys.exit(1)
    
    # Configuration
    INPUT_FILE = '/mnt/user-data/uploads/test_kbid_auction_1.csv'
    OUTPUT_FILE = '/mnt/user-data/outputs/auction_analysis_results'
    
    # For demo, analyze first 10 items (remove max_items for full analysis)
    MAX_ITEMS = 10
    MIN_OPPORTUNITY_SCORE = 20  # Only show items with score >= 20
    
    # Run analysis
    analyzer = AuctionAnalyzer(api_key)
    
    analyses = analyzer.analyze_auction_file(
        INPUT_FILE,
        OUTPUT_FILE,
        max_items=MAX_ITEMS,
        min_opportunity_score=MIN_OPPORTUNITY_SCORE
    )
    
    analyzer.print_summary(analyses)
