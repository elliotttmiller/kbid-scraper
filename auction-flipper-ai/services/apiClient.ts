import { AnalyzedItem, AuctionItem, MarketResearch, ProfitAnalysis } from '../types';

const API_BASE = (import.meta.env.VITE_AUCTION_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');

type EngineResult = {
  item: { external_id: string; condition: string; category: string };
  market: { high_price: number; median_price: number; sold_count: number; confidence: number; liquidity: number };
  costs: { total_cost: number };
  evidence: Array<{ url: string }>;
  expected_sell_price: number;
  expected_profit: number;
  expected_roi: number;
  maximum_bid: number;
  break_even_sell_price: number;
  opportunity_score: number;
  risk_score: number;
  recommendation: 'STRONG_BUY' | 'BUY' | 'WATCH' | 'PASS' | 'RESEARCH';
  risk_factors: string[];
  analyzed_at: string;
};

const request = async <T>(path: string, body?: unknown): Promise<T> => {
  const response = await fetch(`${API_BASE}${path}`, {
    method: body ? 'POST' : 'GET',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `Auction engine returned HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
};

const mapResult = (original: AuctionItem, result: EngineResult): AnalyzedItem => {
  const marketResearch: MarketResearch = {
    retailPrice: result.market.high_price,
    usedPrice: result.market.median_price,
    ebaySoldAvg: result.market.sold_count > 0 ? result.market.median_price : 0,
    demandScore: Math.round(result.market.confidence * 10),
    liquidityScore: Math.round(result.market.liquidity * 10),
    conditionNotes: result.item.condition,
    compLinks: result.evidence.map(comp => comp.url).filter(Boolean),
    lastUpdated: result.analyzed_at,
    confidence: result.market.confidence,
    soldCompCount: result.market.sold_count,
  };
  const profitAnalysis: ProfitAnalysis = {
    estimatedSellPrice: result.expected_sell_price,
    totalCost: result.costs.total_cost,
    netProfit: result.expected_profit,
    roi: result.expected_roi,
    opportunityScore: result.opportunity_score,
    recommendation: result.recommendation,
    riskScore: result.risk_score,
    riskFactors: result.risk_factors,
    maximumBid: result.maximum_bid,
    breakEvenSellPrice: result.break_even_sell_price,
  };
  return {
    ...original,
    category: result.item.category || original.category,
    condition: result.item.condition || original.condition,
    marketResearch,
    profitAnalysis,
    status: 'complete',
  };
};

export const analyzeItems = async (items: AuctionItem[]): Promise<AnalyzedItem[]> => {
  const { results } = await request<{ results: EngineResult[] }>('/api/v1/analyze', { items });
  const originals = new Map(items.map(item => [item.id, item]));
  return results.flatMap(result => {
    const original = originals.get(result.item.external_id);
    return original ? [mapResult(original, result)] : [];
  });
};

export const deepRiskAnalysis = async (item: AuctionItem): Promise<string> => {
  const payload = await request<{ report: string }>('/api/v1/deep-risk', { item });
  return payload.report;
};

export const portfolioChat = async (items: AnalyzedItem[], question: string): Promise<string> => {
  const payload = await request<{ answer: string }>('/api/v1/chat', { results: items, question });
  return payload.answer;
};
