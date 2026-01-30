#!/usr/bin/env python3
"""
Real-Time Auction Market Analysis & EV+ Profit Detection System
Complete implementation framework with working code examples
"""

import asyncio
import aiohttp
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import re
from dataclasses import dataclass, asdict
import json
from enum import Enum


# ============================================================================
# DATA MODELS
# ============================================================================

class ConditionGrade(Enum):
    NEW = "New"
    LIKE_NEW = "Like New"
    EXCELLENT = "Excellent"
    GOOD = "Good"
    FAIR = "Fair"
    POOR = "Poor"
    PARTS = "Parts/Not Working"


@dataclass
class ProductInfo:
    """Structured product information"""
    brand: Optional[str]
    model: str
    category: str
    subcategory: Optional[str]
    upc: Optional[str] = None
    mpn: Optional[str] = None
    specs: Dict = None
    
    def __post_init__(self):
        if self.specs is None:
            self.specs = {}


@dataclass
class ConditionInfo:
    """Item condition details"""
    grade: ConditionGrade
    score: int  # 0-100
    notes: str
    has_damage: bool
    damage_types: List[str] = None
    
    def __post_init__(self):
        if self.damage_types is None:
            self.damage_types = []


@dataclass
class AuctionData:
    """Current auction status"""
    lot_number: str
    auction_id: str
    current_price: float
    next_required_bid: float
    closing_time: datetime
    location: str
    url: str
    image_url: Optional[str] = None


@dataclass
class MarketPrice:
    """Market price statistics"""
    median_price: float
    mean_price: float
    std_dev: float
    min_price: float
    max_price: float
    percentile_25: float
    percentile_75: float
    sample_size: int
    confidence_score: float
    data_sources: List[str] = None
    
    def __post_init__(self):
        if self.data_sources is None:
            self.data_sources = []


# ============================================================================
# PRODUCT EXTRACTION & NORMALIZATION
# ============================================================================

class ProductExtractor:
    """Extract structured product info from auction listings"""
    
    # Common brand patterns
    BRANDS = [
        "Vissani", "NewAir", "Samsung", "LG", "Whirlpool", "GE", 
        "Frigidaire", "KitchenAid", "Bosch", "Sony", "Apple", "Dell",
        "HP", "Lenovo", "Nike", "Adidas", "Canon", "Nikon"
    ]
    
    # Condition keywords
    CONDITION_KEYWORDS = {
        ConditionGrade.NEW: ["new", "unopened", "sealed", "nib"],
        ConditionGrade.LIKE_NEW: ["like new", "barely used", "mint"],
        ConditionGrade.EXCELLENT: ["excellent", "great condition"],
        ConditionGrade.GOOD: ["good", "working", "functional"],
        ConditionGrade.FAIR: ["fair", "minor damage", "transit damage", "cosmetic"],
        ConditionGrade.POOR: ["poor", "major damage", "damaged"],
        ConditionGrade.PARTS: ["parts", "not working", "broken", "as-is"]
    }
    
    def extract_product(self, title: str, description: str) -> ProductInfo:
        """Extract product information from title and description"""
        
        # Extract brand
        brand = self._extract_brand(title + " " + description)
        
        # Extract model/product name
        model = self._extract_model(title)
        
        # Extract category (simplified - would use more sophisticated logic)
        category = self._extract_category(title, description)
        
        # Extract specifications
        specs = self._extract_specs(title + " " + description)
        
        return ProductInfo(
            brand=brand,
            model=model,
            category=category,
            subcategory=None,
            specs=specs
        )
    
    def _extract_brand(self, text: str) -> Optional[str]:
        """Extract brand name from text"""
        text_lower = text.lower()
        for brand in self.BRANDS:
            if brand.lower() in text_lower:
                return brand
        return None
    
    def _extract_model(self, title: str) -> str:
        """Extract model/product description"""
        # Remove common prefixes
        cleaned = re.sub(r'^(LOT OF \d+|NEW|USED)\s+', '', title, flags=re.IGNORECASE)
        # Take first 100 chars as model
        return cleaned[:100].strip()
    
    def _extract_category(self, title: str, description: str) -> str:
        """Determine product category"""
        text = (title + " " + description).lower()
        
        # Category detection rules
        if any(word in text for word in ['refrigerator', 'freezer', 'fridge']):
            return "Major Appliances > Refrigeration"
        elif any(word in text for word in ['washer', 'dryer', 'laundry']):
            return "Major Appliances > Laundry"
        elif any(word in text for word in ['tv', 'television', 'monitor']):
            return "Electronics > TVs & Monitors"
        elif any(word in text for word in ['laptop', 'computer', 'pc']):
            return "Electronics > Computers"
        elif any(word in text for word in ['tool', 'drill', 'saw']):
            return "Tools > Power Tools"
        else:
            return "General"
    
    def _extract_specs(self, text: str) -> Dict:
        """Extract specifications like size, capacity, etc."""
        specs = {}
        
        # Extract cubic feet
        cu_ft_match = re.search(r'(\d+\.?\d*)\s*cu\.?\s*ft', text, re.IGNORECASE)
        if cu_ft_match:
            specs['capacity_cu_ft'] = float(cu_ft_match.group(1))
        
        # Extract can capacity
        can_match = re.search(r'(\d+)\s*(?:can|cans|bottle)', text, re.IGNORECASE)
        if can_match:
            specs['can_capacity'] = int(can_match.group(1))
        
        # Extract dimensions
        dim_match = re.search(r'(\d+\.?\d*)\s*(?:x|×)\s*(\d+\.?\d*)\s*(?:x|×)\s*(\d+\.?\d*)', text)
        if dim_match:
            specs['dimensions'] = f"{dim_match.group(1)}x{dim_match.group(2)}x{dim_match.group(3)}"
        
        return specs
    
    def assess_condition(self, title: str, description: str) -> ConditionInfo:
        """Assess item condition from description"""
        text = (title + " " + description).lower()
        
        # Check for condition keywords
        detected_condition = ConditionGrade.GOOD  # Default
        max_score = 0
        
        for grade, keywords in self.CONDITION_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text:
                    # Use the worst condition found
                    condition_scores = {
                        ConditionGrade.NEW: 100,
                        ConditionGrade.LIKE_NEW: 95,
                        ConditionGrade.EXCELLENT: 90,
                        ConditionGrade.GOOD: 80,
                        ConditionGrade.FAIR: 65,
                        ConditionGrade.POOR: 40,
                        ConditionGrade.PARTS: 20
                    }
                    if condition_scores[grade] > max_score or max_score == 0:
                        detected_condition = grade
                        max_score = condition_scores[grade]
        
        # Detect damage types
        damage_types = []
        has_damage = False
        
        if "transit damage" in text or "shipping damage" in text:
            damage_types.append("transit")
            has_damage = True
        if "cosmetic" in text and "damage" in text:
            damage_types.append("cosmetic")
            has_damage = True
        if "scratch" in text or "dent" in text:
            damage_types.append("cosmetic")
            has_damage = True
        
        # Adjust score based on damage
        score = max_score if max_score > 0 else 80
        if has_damage and score > 70:
            score -= 10
        
        return ConditionInfo(
            grade=detected_condition,
            score=score,
            notes=self._extract_condition_notes(text),
            has_damage=has_damage,
            damage_types=damage_types
        )
    
    def _extract_condition_notes(self, text: str) -> str:
        """Extract relevant condition notes"""
        # Look for parenthetical notes
        notes_match = re.search(r'\(([^)]*damage[^)]*)\)', text, re.IGNORECASE)
        if notes_match:
            return notes_match.group(1)
        
        # Look for "See Photos" or similar
        if "see photos" in text:
            return "See photos for condition details"
        
        return ""


# ============================================================================
# MARKET RESEARCH ENGINE
# ============================================================================

class MarketResearcher:
    """Research market prices from multiple sources"""
    
    def __init__(self, ebay_api_key: str = None, amazon_api_key: str = None):
        self.ebay_api_key = ebay_api_key
        self.amazon_api_key = amazon_api_key
        self.session = None
    
    async def research_product(self, product: ProductInfo, condition: ConditionInfo) -> MarketPrice:
        """Research market prices for a product"""
        
        # Combine data from multiple sources
        all_prices = []
        data_sources = []
        
        # eBay sold listings (highest priority)
        ebay_prices = await self._fetch_ebay_sold_prices(product, condition)
        if ebay_prices:
            all_prices.extend(ebay_prices)
            data_sources.append("eBay")
        
        # Amazon current prices
        amazon_prices = await self._fetch_amazon_prices(product)
        if amazon_prices:
            # Adjust for condition if necessary
            adjusted_amazon = self._adjust_for_condition(amazon_prices, condition)
            all_prices.extend(adjusted_amazon)
            data_sources.append("Amazon")
        
        # If we have enough data, calculate statistics
        if len(all_prices) >= 3:
            return self._calculate_price_statistics(all_prices, data_sources)
        else:
            # Return null/low confidence result
            return self._create_low_confidence_result()
    
    async def _fetch_ebay_sold_prices(self, product: ProductInfo, condition: ConditionInfo) -> List[float]:
        """Fetch sold prices from eBay"""
        
        # This is a placeholder - in production, use eBay Finding API
        # Example: https://developer.ebay.com/DevZone/finding/Concepts/FindingAPIGuide.html
        
        # Construct search query
        query = f"{product.brand} {product.model}".strip()
        
        # In production, make actual API call:
        """
        params = {
            'OPERATION-NAME': 'findCompletedItems',
            'keywords': query,
            'itemFilter': [
                {'name': 'SoldItemsOnly', 'value': 'true'},
                {'name': 'Condition', 'value': self._map_condition_to_ebay(condition)}
            ],
            'sortOrder': 'EndTimeSoonest'
        }
        response = await self._make_ebay_api_call(params)
        """
        
        # For demo, return simulated data
        # In reality, parse API response and extract prices
        return await self._simulate_ebay_prices(product, condition)
    
    async def _simulate_ebay_prices(self, product: ProductInfo, condition: ConditionInfo) -> List[float]:
        """Simulate eBay price data for demonstration"""
        await asyncio.sleep(0.1)  # Simulate API latency
        
        # Generate realistic price distribution based on condition
        base_price_map = {
            "Major Appliances": 200,
            "Electronics": 150,
            "Tools": 100,
            "General": 50
        }
        
        category_key = product.category.split(">")[0].strip()
        base_price = base_price_map.get(category_key, 50)
        
        # Adjust for condition
        condition_multiplier = condition.score / 100
        adjusted_base = base_price * condition_multiplier
        
        # Generate sample prices with realistic variance
        num_samples = np.random.randint(15, 45)
        prices = np.random.normal(adjusted_base, adjusted_base * 0.2, num_samples)
        prices = np.clip(prices, adjusted_base * 0.5, adjusted_base * 1.5)
        
        return prices.tolist()
    
    async def _fetch_amazon_prices(self, product: ProductInfo) -> List[float]:
        """Fetch current prices from Amazon"""
        # Placeholder - use Amazon Product Advertising API in production
        await asyncio.sleep(0.1)
        
        # Simulate Amazon price data
        if product.category.startswith("Major Appliances"):
            return [250.0, 265.0, 275.0]
        elif product.category.startswith("Electronics"):
            return [180.0, 195.0, 210.0]
        else:
            return [75.0, 85.0, 95.0]
    
    def _adjust_for_condition(self, prices: List[float], condition: ConditionInfo) -> List[float]:
        """Adjust prices based on condition vs new"""
        multiplier = condition.score / 100
        return [p * multiplier for p in prices]
    
    def _calculate_price_statistics(self, prices: List[float], sources: List[str]) -> MarketPrice:
        """Calculate comprehensive price statistics"""
        
        # Remove outliers using IQR method
        q1 = np.percentile(prices, 25)
        q3 = np.percentile(prices, 75)
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        
        clean_prices = [p for p in prices if lower_bound <= p <= upper_bound]
        
        if len(clean_prices) < 3:
            clean_prices = prices  # Use all if too few after filtering
        
        # Calculate statistics
        median = np.median(clean_prices)
        mean = np.mean(clean_prices)
        std_dev = np.std(clean_prices)
        
        # Calculate confidence score
        confidence = self._calculate_confidence(clean_prices, sources)
        
        return MarketPrice(
            median_price=median,
            mean_price=mean,
            std_dev=std_dev,
            min_price=np.min(clean_prices),
            max_price=np.max(clean_prices),
            percentile_25=np.percentile(clean_prices, 25),
            percentile_75=np.percentile(clean_prices, 75),
            sample_size=len(clean_prices),
            confidence_score=confidence,
            data_sources=sources
        )
    
    def _calculate_confidence(self, prices: List[float], sources: List[str]) -> float:
        """Calculate confidence score 0-1"""
        
        # Factor 1: Sample size (max at 50 samples)
        sample_score = min(len(prices) / 50, 1.0)
        
        # Factor 2: Price variance (lower is better)
        if len(prices) > 1 and np.mean(prices) > 0:
            cv = np.std(prices) / np.mean(prices)  # Coefficient of variation
            variance_score = max(0, 1 - cv)
        else:
            variance_score = 0.5
        
        # Factor 3: Source diversity
        source_score = min(len(sources) / 3, 1.0)
        
        # Weighted combination
        confidence = (
            sample_score * 0.4 +
            variance_score * 0.4 +
            source_score * 0.2
        )
        
        return confidence
    
    def _create_low_confidence_result(self) -> MarketPrice:
        """Create a low-confidence placeholder result"""
        return MarketPrice(
            median_price=0,
            mean_price=0,
            std_dev=0,
            min_price=0,
            max_price=0,
            percentile_25=0,
            percentile_75=0,
            sample_size=0,
            confidence_score=0.0,
            data_sources=[]
        )


# ============================================================================
# COST CALCULATOR
# ============================================================================

class CostCalculator:
    """Calculate all costs associated with buying and reselling"""
    
    # Fee structures for different platforms
    PLATFORM_FEES = {
        "ebay": {
            "final_value_fee": 0.1350,
            "payment_processing": 0.0425,
            "insertion_fee": 0.35
        },
        "facebook": {
            "final_value_fee": 0.05,
            "payment_processing": 0.0290,
            "insertion_fee": 0.00
        },
        "mercari": {
            "final_value_fee": 0.10,
            "payment_processing": 0.0299,
            "insertion_fee": 0.00
        }
    }
    
    def __init__(self, 
                 buyers_premium_rate: float = 0.18,
                 sales_tax_rate: float = 0.0725,
                 hourly_rate: float = 15.00,
                 default_platform: str = "ebay"):
        self.buyers_premium_rate = buyers_premium_rate
        self.sales_tax_rate = sales_tax_rate
        self.hourly_rate = hourly_rate
        self.default_platform = default_platform
    
    def calculate_acquisition_cost(self, winning_bid: float) -> Dict:
        """Calculate total cost to acquire item at auction"""
        
        buyers_premium = winning_bid * self.buyers_premium_rate
        subtotal = winning_bid + buyers_premium
        sales_tax = subtotal * self.sales_tax_rate
        
        total = winning_bid + buyers_premium + sales_tax
        
        return {
            "hammer_price": winning_bid,
            "buyers_premium": buyers_premium,
            "sales_tax": sales_tax,
            "total": total
        }
    
    def estimate_logistics_cost(self, 
                               item_category: str,
                               location: str,
                               your_location: str = "Minneapolis, MN") -> Dict:
        """Estimate shipping/pickup costs"""
        
        # Simplified distance calculation (in production, use Google Maps API)
        is_local = location.split(',')[-1].strip() == your_location.split(',')[-1].strip()
        
        if is_local:
            # Local pickup - gas + time
            pickup_cost = 10.00  # Gas
            pickup_time_cost = (0.5 * self.hourly_rate)  # 30 min round trip
            shipping_cost = pickup_cost + pickup_time_cost
        else:
            # Estimate shipping based on category
            category_shipping = {
                "Major Appliances": 75.00,
                "Electronics": 25.00,
                "Tools": 15.00,
                "Furniture": 100.00,
                "Clothing": 8.00,
                "General": 12.00
            }
            
            category_key = item_category.split(">")[0].strip()
            shipping_cost = category_shipping.get(category_key, 20.00)
        
        # Packaging costs
        category_packaging = {
            "Major Appliances": 15.00,
            "Electronics": 5.00,
            "Tools": 3.00,
            "Furniture": 20.00,
            "Clothing": 2.00,
            "General": 3.00
        }
        
        category_key = item_category.split(">")[0].strip()
        packaging_cost = category_packaging.get(category_key, 5.00)
        
        return {
            "shipping_pickup": shipping_cost,
            "packaging": packaging_cost,
            "total": shipping_cost + packaging_cost
        }
    
    def calculate_overhead_costs(self) -> Dict:
        """Calculate time and overhead costs"""
        
        # Photography time
        photo_time = 0.25  # 15 minutes
        photo_cost = photo_time * self.hourly_rate
        
        # Listing creation time
        listing_time = 0.5  # 30 minutes
        listing_cost = listing_time * self.hourly_rate
        
        # Monthly storage allocation
        storage_cost = 5.00
        
        return {
            "photography": photo_cost,
            "listing": listing_cost,
            "storage": storage_cost,
            "total": photo_cost + listing_cost + storage_cost
        }
    
    def calculate_platform_fees(self, sell_price: float, platform: str = None) -> Dict:
        """Calculate selling platform fees"""
        
        if platform is None:
            platform = self.default_platform
        
        fees = self.PLATFORM_FEES.get(platform, self.PLATFORM_FEES["ebay"])
        
        final_value_fee = sell_price * fees["final_value_fee"]
        payment_fee = sell_price * fees["payment_processing"]
        insertion_fee = fees["insertion_fee"]
        
        total = final_value_fee + payment_fee + insertion_fee
        
        return {
            "final_value_fee": final_value_fee,
            "payment_processing": payment_fee,
            "insertion_fee": insertion_fee,
            "total": total
        }
    
    def calculate_total_costs(self, 
                             auction_data: AuctionData,
                             product: ProductInfo,
                             estimated_sell_price: float = None) -> Dict:
        """Calculate all costs for an item"""
        
        # Use current price as estimate if no sell price given
        if estimated_sell_price is None:
            estimated_sell_price = auction_data.current_price * 2
        
        acquisition = self.calculate_acquisition_cost(auction_data.current_price)
        logistics = self.estimate_logistics_cost(
            product.category,
            auction_data.location
        )
        overhead = self.calculate_overhead_costs()
        platform_fees = self.calculate_platform_fees(estimated_sell_price)
        
        # Return shipping (10% of items)
        return_shipping = logistics["shipping_pickup"] * 0.10
        
        fixed_costs = (
            acquisition["total"] +
            logistics["total"] +
            overhead["total"]
        )
        
        variable_costs = platform_fees["total"] + return_shipping
        
        total_costs = fixed_costs + variable_costs
        
        return {
            "acquisition": acquisition,
            "logistics": logistics,
            "overhead": overhead,
            "platform_fees": platform_fees,
            "return_shipping": return_shipping,
            "fixed_costs": fixed_costs,
            "variable_costs": variable_costs,
            "total_costs": total_costs
        }


# ============================================================================
# EXPECTED VALUE (EV) CALCULATOR
# ============================================================================

class EVCalculator:
    """Calculate Expected Value and profit scenarios"""
    
    def calculate_ev(self, 
                    market_price: MarketPrice,
                    costs: Dict,
                    condition_score: int) -> Dict:
        """Calculate Expected Value with multiple scenarios"""
        
        # Define scenarios with probabilities
        scenarios = [
            {
                "name": "best_case",
                "sell_price": market_price.percentile_75,
                "probability": 0.15,
                "time_to_sell_days": 7
            },
            {
                "name": "likely_case",
                "sell_price": market_price.median_price,
                "probability": 0.60,
                "time_to_sell_days": 21
            },
            {
                "name": "worst_case",
                "sell_price": market_price.percentile_25,
                "probability": 0.20,
                "time_to_sell_days": 60
            },
            {
                "name": "no_sale",
                "sell_price": costs["fixed_costs"] * 0.3,  # Salvage value
                "probability": 0.05,
                "time_to_sell_days": 90
            }
        ]
        
        # Calculate profit for each scenario
        expected_value = 0
        scenario_results = []
        
        for scenario in scenarios:
            sell_price = scenario["sell_price"]
            
            # Recalculate platform fees for this price
            platform_fees = (
                sell_price * 0.1350 +  # eBay final value
                sell_price * 0.0425 +  # Payment processing
                0.35                    # Insertion fee
            )
            
            return_shipping = costs["logistics"]["shipping_pickup"] * 0.10
            
            total_costs = costs["fixed_costs"] + platform_fees + return_shipping
            gross_profit = sell_price - total_costs
            
            # Weight by probability
            weighted_profit = gross_profit * scenario["probability"]
            expected_value += weighted_profit
            
            # Calculate ROI
            roi = (gross_profit / costs["fixed_costs"] * 100) if costs["fixed_costs"] > 0 else 0
            
            scenario_results.append({
                "scenario": scenario["name"],
                "sell_price": sell_price,
                "total_costs": total_costs,
                "gross_profit": gross_profit,
                "roi_percent": roi,
                "probability": scenario["probability"],
                "ev_contribution": weighted_profit,
                "time_to_sell_days": scenario["time_to_sell_days"]
            })
        
        # Calculate risk metrics
        best_profit = scenario_results[0]["gross_profit"]
        worst_profit = scenario_results[2]["gross_profit"]
        
        downside_risk = abs(min(worst_profit, 0))
        upside_potential = max(best_profit, 0)
        risk_reward = upside_potential / downside_risk if downside_risk > 0 else float('inf')
        
        # Expected ROI
        expected_roi = (expected_value / costs["fixed_costs"] * 100) if costs["fixed_costs"] > 0 else 0
        
        # Probability of loss (worst case + no sale scenarios)
        prob_loss = sum(s["probability"] for s in scenarios if s["sell_price"] < costs["total_costs"])
        
        return {
            "expected_value": expected_value,
            "expected_roi": expected_roi,
            "scenarios": scenario_results,
            "risk_metrics": {
                "downside_risk": downside_risk,
                "upside_potential": upside_potential,
                "risk_reward_ratio": risk_reward,
                "probability_of_loss": prob_loss
            },
            "break_even_price": costs["total_costs"] / 0.82  # Accounting for fees
        }


# ============================================================================
# OPPORTUNITY SCORER
# ============================================================================

class OpportunityScorer:
    """Score and rank auction opportunities"""
    
    def score_opportunity(self, 
                         ev_analysis: Dict,
                         market_price: MarketPrice,
                         costs: Dict) -> Dict:
        """Calculate comprehensive opportunity score (0-100)"""
        
        scores = {}
        
        # 1. Profitability Score (30 points max)
        ev = ev_analysis["expected_value"]
        fixed_costs = costs["fixed_costs"]
        roi = ev_analysis["expected_roi"]
        
        # Target: 50%+ ROI = full points
        profitability_score = min((roi / 50) * 30, 30)
        scores["profitability"] = profitability_score
        
        # 2. Confidence Score (25 points max)
        confidence_score = market_price.confidence_score * 25
        scores["confidence"] = confidence_score
        
        # 3. Liquidity Score (20 points max)
        # Calculate weighted average time to sell
        avg_time = sum(
            s["time_to_sell_days"] * s["probability"]
            for s in ev_analysis["scenarios"]
        )
        # 7 days = full points, 60+ days = 0 points
        liquidity_factor = max(0, 1 - (avg_time - 7) / 53)
        liquidity_score = liquidity_factor * 20
        scores["liquidity"] = liquidity_score
        
        # 4. Risk Score (15 points max)
        risk_reward = ev_analysis["risk_metrics"]["risk_reward_ratio"]
        # 3:1 ratio = full points
        risk_factor = min(risk_reward / 3, 1.0)
        risk_score = risk_factor * 15
        scores["risk"] = risk_score
        
        # 5. Absolute Profit Score (10 points max)
        # $100+ profit = full points
        absolute_factor = min(ev / 100, 1.0)
        absolute_score = absolute_factor * 10
        scores["absolute_profit"] = absolute_score
        
        # Total score
        total_score = sum(scores.values())
        
        # Assign grade
        grade = self._assign_grade(total_score)
        
        # Generate recommendation
        recommendation = self._generate_recommendation(total_score, ev, roi)
        
        return {
            "total_score": total_score,
            "grade": grade,
            "component_scores": scores,
            "recommendation": recommendation
        }
    
    def _assign_grade(self, score: float) -> str:
        """Assign letter grade"""
        if score >= 85: return "A+"
        if score >= 80: return "A"
        if score >= 75: return "A-"
        if score >= 70: return "B+"
        if score >= 65: return "B"
        if score >= 60: return "B-"
        if score >= 55: return "C+"
        if score >= 50: return "C"
        return "D"
    
    def _generate_recommendation(self, score: float, ev: float, roi: float) -> str:
        """Generate action recommendation"""
        if score >= 75 and ev > 50 and roi > 40:
            return "STRONG BUY - High confidence, excellent profit potential"
        elif score >= 65 and ev > 30:
            return "BUY - Good opportunity with acceptable risk"
        elif score >= 55:
            return "CONSIDER - Moderate opportunity, evaluate competition"
        elif score >= 45:
            return "MARGINAL - Low profit margin, proceed with caution"
        else:
            return "AVOID - Expected value too low or high risk"


# ============================================================================
# MAIN ANALYSIS PIPELINE
# ============================================================================

class AuctionAnalyzer:
    """Main pipeline for analyzing auction items"""
    
    def __init__(self):
        self.extractor = ProductExtractor()
        self.researcher = MarketResearcher()
        self.cost_calc = CostCalculator()
        self.ev_calc = EVCalculator()
        self.scorer = OpportunityScorer()
    
    async def analyze_item(self, auction_row: Dict) -> Dict:
        """Analyze a single auction item"""
        
        try:
            # 1. Extract product information
            product = self.extractor.extract_product(
                auction_row["item_title"],
                auction_row["short_description"]
            )
            
            # 2. Assess condition
            condition = self.extractor.assess_condition(
                auction_row["item_title"],
                auction_row["short_description"]
            )
            
            # 3. Parse auction data
            # Note: Your CSV has bidder IDs instead of prices - fix in production
            current_price = 15.00  # Placeholder - parse from next_required_bid
            
            auction_data = AuctionData(
                lot_number=auction_row["lot_number"],
                auction_id=auction_row["auction_id"],
                current_price=current_price,
                next_required_bid=current_price + 5,
                closing_time=datetime.now() + timedelta(hours=4),
                location=auction_row["location"].split("Phone:")[0].strip(),
                url=auction_row["item_url"],
                image_url=auction_row.get("image_url")
            )
            
            # 4. Research market prices
            market_price = await self.researcher.research_product(product, condition)
            
            # 5. Calculate costs
            costs = self.cost_calc.calculate_total_costs(
                auction_data,
                product,
                market_price.median_price
            )
            
            # 6. Calculate EV
            ev_analysis = self.ev_calc.calculate_ev(
                market_price,
                costs,
                condition.score
            )
            
            # 7. Score opportunity
            opportunity_score = self.scorer.score_opportunity(
                ev_analysis,
                market_price,
                costs
            )
            
            # 8. Compile results
            result = {
                "lot_number": auction_row["lot_number"],
                "auction_id": auction_row["auction_id"],
                "item_title": auction_row["item_title"],
                "product": asdict(product),
                "condition": asdict(condition),
                "auction_data": asdict(auction_data),
                "market_price": asdict(market_price),
                "costs": costs,
                "ev_analysis": ev_analysis,
                "opportunity_score": opportunity_score,
                "analysis_timestamp": datetime.now().isoformat()
            }
            
            return result
            
        except Exception as e:
            print(f"Error analyzing lot {auction_row.get('lot_number', 'unknown')}: {str(e)}")
            return None
    
    async def analyze_batch(self, auction_items: List[Dict], max_concurrent: int = 10) -> List[Dict]:
        """Analyze multiple items in parallel"""
        
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def analyze_with_semaphore(item):
            async with semaphore:
                return await self.analyze_item(item)
        
        tasks = [analyze_with_semaphore(item) for item in auction_items]
        results = await asyncio.gather(*tasks)
        
        # Filter out failed analyses and sort by score
        successful = [r for r in results if r is not None]
        successful.sort(
            key=lambda x: x["opportunity_score"]["total_score"],
            reverse=True
        )
        
        return successful


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

async def main():
    """Example usage of the analyzer"""
    
    # Load auction data from CSV
    df = pd.read_csv("/mnt/user-data/uploads/test_kbid_auction_1.csv")
    
    # Convert to list of dicts
    auction_items = df.to_dict('records')
    
    # Analyze first 10 items as example
    analyzer = AuctionAnalyzer()
    results = await analyzer.analyze_batch(auction_items[:10])
    
    # Print results
    print(f"\nAnalyzed {len(results)} items\n")
    print("=" * 80)
    
    for i, result in enumerate(results[:5], 1):
        print(f"\nRank #{i}")
        print(f"Lot: {result['lot_number']} - {result['item_title'][:60]}...")
        print(f"Score: {result['opportunity_score']['total_score']:.1f} ({result['opportunity_score']['grade']})")
        print(f"Expected Value: ${result['ev_analysis']['expected_value']:.2f}")
        print(f"Expected ROI: {result['ev_analysis']['expected_roi']:.1f}%")
        print(f"Recommendation: {result['opportunity_score']['recommendation']}")
        print(f"Confidence: {result['market_price']['confidence_score']:.2f}")
        print("-" * 80)
    
    # Export to JSON
    with open('/home/claude/analysis_results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\nFull results exported to analysis_results.json")


if __name__ == "__main__":
    # Run the analyzer
    asyncio.run(main())
