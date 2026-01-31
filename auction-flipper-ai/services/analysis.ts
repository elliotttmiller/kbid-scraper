import { AnalyzedItem, MarketResearch, ProfitAnalysis, Settings } from "../types";

export const calculateProfitability = (
  item: AnalyzedItem,
  research: MarketResearch,
  settings: Settings
): ProfitAnalysis => {
  const { currentBid, shippingCost } = item;
  const actualShipping = shippingCost || settings.shippingDefault;
  
  // Determine realistic sell price (conservative estimate: usually lower of used/ebay avg)
  // Weighted slightly towards eBay sold as it's most liquid
  const estimatedSellPrice = research.ebaySoldAvg > 0 
    ? research.ebaySoldAvg 
    : research.usedPrice * 0.9;

  // Costs
  const platformFee = estimatedSellPrice * settings.platformFeeRate;
  const acquisitionCost = currentBid + actualShipping;
  const totalCost = acquisitionCost + platformFee;
  
  const netProfit = estimatedSellPrice - totalCost;
  const roi = acquisitionCost > 0 ? (netProfit / acquisitionCost) * 100 : 0;

  // Scoring Logic (0-100)
  // 1. Profit Score (Max 40): $100 profit = 40 pts
  const profitScore = Math.min(40, (netProfit / settings.minProfit) * 20);
  
  // 2. ROI Score (Max 30): 100% ROI = 30 pts
  const roiScore = Math.min(30, (roi / settings.minRoi) * 15);
  
  // 3. Demand Score (Max 20): score * 2
  const demandScorePart = (research.demandScore || 5) * 2;
  
  // 4. Liquidity Score (Max 10): score * 1
  const liquidityScorePart = (research.liquidityScore || 5) * 1;

  let totalScore = profitScore + roiScore + demandScorePart + liquidityScorePart;
  
  // Risk Penalties
  const riskFactors: string[] = [];
  if (roi < 15) {
    totalScore -= 10;
    riskFactors.push("Low ROI (<15%)");
  }
  if (research.liquidityScore < 4) {
    totalScore -= 15;
    riskFactors.push("Low Liquidity");
  }
  if (research.demandScore < 4) {
    totalScore -= 10;
    riskFactors.push("Low Demand");
  }
  if (item.condition.toLowerCase().includes('damage') || item.condition.toLowerCase().includes('parts')) {
    totalScore -= 20;
    riskFactors.push("Condition Risk (Damaged/Parts)");
  }

  const finalScore = Math.max(0, Math.min(100, totalScore));
  
  // Recommendation
  let recommendation: ProfitAnalysis['recommendation'] = 'PASS';
  if (finalScore >= 70) recommendation = 'STRONG BUY';
  else if (finalScore >= 50) recommendation = 'BUY';
  else if (finalScore >= 30) recommendation = 'MAYBE';

  // Risk Score (1-10) Inverse of score mostly + specific flags
  let riskScore = 1;
  if (roi < 20) riskScore += 2;
  if (research.liquidityScore < 5) riskScore += 2;
  if (research.demandScore < 5) riskScore += 2;
  if (currentBid > 200) riskScore += 1; // Higher capital risk
  if (item.description.length < 50) riskScore += 1; // Low info risk

  return {
    estimatedSellPrice,
    totalCost,
    netProfit,
    roi,
    opportunityScore: finalScore,
    recommendation,
    riskScore: Math.min(10, riskScore),
    riskFactors
  };
};
