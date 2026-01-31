export interface AuctionItem {
  id: string;
  lotNumber: string;
  title: string;
  groupName: string; // The Auction Title / Lot Name
  description: string;
  currentBid: number;
  category: string;
  condition: string; // e.g., 'New', 'Open Box', 'Used', 'Damaged'
  shippingCost?: number;
  imageUrl?: string;
  itemUrl?: string;
  location?: string;
}

export interface MarketResearch {
  retailPrice: number;
  usedPrice: number;
  ebaySoldAvg: number;
  demandScore: number; // 1-10
  liquidityScore: number; // 1-10
  conditionNotes: string;
  compLinks: string[]; // URLs found during search
  lastUpdated: string;
}

export interface ProfitAnalysis {
  estimatedSellPrice: number;
  totalCost: number; // Bid + Shipping + Fees
  netProfit: number;
  roi: number; // Percentage
  opportunityScore: number; // 0-100
  recommendation: 'STRONG BUY' | 'BUY' | 'MAYBE' | 'PASS';
  riskScore: number; // 1-10
  riskFactors: string[];
}

export interface AnalyzedItem extends AuctionItem {
  marketResearch?: MarketResearch;
  profitAnalysis?: ProfitAnalysis;
  status: 'pending' | 'analyzing' | 'complete' | 'error';
  error?: string;
  deepAnalysis?: string; // For the "Thinking" model output
}

export interface Settings {
  shippingDefault: number;
  platformFeeRate: number; // e.g., 0.13 for eBay
  minRoi: number;
  minProfit: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'model';
  content: string;
  timestamp: Date;
}

export interface AuctionGroupSummary {
  groupName: string;
  totalItems: number;
  analyzedCount: number;
  totalProfit: number;
  avgRoi: number;
  bestItem?: AnalyzedItem;
  status: 'pending' | 'processing' | 'complete';
  coverImage?: string;
  location?: string;
}