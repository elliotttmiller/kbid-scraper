import React, { useState } from 'react';
import { AnalyzedItem } from '../types';
import { X, ExternalLink, ShieldAlert, BrainCircuit, Check, Image as ImageIcon } from 'lucide-react';
import { performDeepRiskAnalysis } from '../services/geminiService';

interface ItemDetailModalProps {
  item: AnalyzedItem | null;
  onClose: () => void;
  onUpdateItem: (item: AnalyzedItem) => void;
}

const ItemDetailModal: React.FC<ItemDetailModalProps> = ({ item, onClose, onUpdateItem }) => {
  const [isThinking, setIsThinking] = useState(false);

  if (!item) return null;

  const handleDeepAnalysis = async () => {
    setIsThinking(true);
    try {
      const result = await performDeepRiskAnalysis(item);
      onUpdateItem({ ...item, deepAnalysis: result });
    } catch (e) {
      console.error(e);
      alert("Deep analysis failed. Please try again.");
    } finally {
      setIsThinking(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4 backdrop-blur-sm">
      <div className="bg-slate-900 rounded-xl shadow-2xl w-full max-w-4xl max-h-[90vh] overflow-y-auto flex flex-col border border-slate-800">
        {/* Header */}
        <div className="p-6 border-b border-slate-800 flex justify-between items-start sticky top-0 bg-slate-900 z-10">
          <div className="flex gap-4">
             {item.imageUrl && (
                <div className="w-16 h-16 rounded-md bg-slate-800 border border-slate-700 overflow-hidden flex-shrink-0">
                  <img src={item.imageUrl} alt={item.title} className="w-full h-full object-cover" />
                </div>
             )}
             <div>
               <h2 className="text-2xl font-bold text-slate-100 line-clamp-2">{item.title}</h2>
               <div className="flex items-center gap-3 mt-2 text-sm text-slate-400">
                 <span className="bg-slate-800 px-2 py-1 rounded text-slate-300 border border-slate-700">Lot #{item.lotNumber}</span>
                 <span>{item.location || item.category}</span>
                 {item.itemUrl && (
                   <a href={item.itemUrl} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 text-blue-400 hover:text-blue-300">
                     <ExternalLink size={14} /> View Auction
                   </a>
                 )}
               </div>
             </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-800 rounded-full transition-colors">
            <X size={24} className="text-slate-500" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 grid grid-cols-1 md:grid-cols-2 gap-8">
          
          {/* Left Column: Financials & Data */}
          <div className="space-y-6">
            <div className="bg-slate-950 p-5 rounded-lg border border-slate-800">
              <h3 className="text-lg font-semibold mb-4 text-slate-200">Profit Analysis</h3>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-xs text-slate-500">Current Bid</div>
                  <div className="text-xl font-medium text-slate-200">${item.currentBid.toFixed(2)}</div>
                </div>
                <div>
                  <div className="text-xs text-slate-500">Est. Sell Price</div>
                  <div className="text-xl font-medium text-slate-200">${item.profitAnalysis?.estimatedSellPrice.toFixed(2)}</div>
                </div>
                <div>
                  <div className="text-xs text-slate-500">Net Profit</div>
                  <div className={`text-xl font-bold ${item.profitAnalysis?.netProfit && item.profitAnalysis.netProfit > 0 ? 'text-green-400' : 'text-red-400'}`}>
                    ${item.profitAnalysis?.netProfit.toFixed(2)}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-slate-500">ROI</div>
                  <div className={`text-xl font-bold ${item.profitAnalysis?.roi && item.profitAnalysis.roi > 20 ? 'text-green-400' : 'text-slate-400'}`}>
                    {item.profitAnalysis?.roi.toFixed(1)}%
                  </div>
                </div>
              </div>
            </div>

            <div className="border border-slate-800 rounded-lg p-5 bg-slate-900">
               <h3 className="text-lg font-semibold mb-4 text-slate-200">Market Research</h3>
               <div className="space-y-3 text-sm">
                  <div className="flex justify-between">
                    <span className="text-slate-500">Retail Price (New)</span>
                    <span className="font-medium text-slate-300">${item.marketResearch?.retailPrice.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Used Market Avg</span>
                    <span className="font-medium text-slate-300">${item.marketResearch?.usedPrice.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">eBay Sold Avg</span>
                    <span className="font-medium text-slate-300">${item.marketResearch?.ebaySoldAvg.toFixed(2)}</span>
                  </div>
                  
                  <div className="pt-2 border-t border-slate-800 mt-2">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-slate-500">Demand Score</span>
                      <div className="flex gap-1">
                        {[...Array(10)].map((_, i) => (
                          <div key={i} className={`w-2 h-2 rounded-full ${i < (item.marketResearch?.demandScore || 0) ? 'bg-blue-500' : 'bg-slate-700'}`} />
                        ))}
                      </div>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-slate-500">Liquidity Score</span>
                      <div className="flex gap-1">
                        {[...Array(10)].map((_, i) => (
                          <div key={i} className={`w-2 h-2 rounded-full ${i < (item.marketResearch?.liquidityScore || 0) ? 'bg-green-500' : 'bg-slate-700'}`} />
                        ))}
                      </div>
                    </div>
                  </div>
               </div>
            </div>

            <div>
              <h3 className="text-sm font-semibold text-slate-400 mb-2">Sources Found</h3>
              <div className="flex flex-wrap gap-2">
                {item.marketResearch?.compLinks.map((link, idx) => (
                  <a 
                    key={idx} 
                    href={link} 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="flex items-center gap-1 text-xs bg-slate-800 hover:bg-slate-700 text-blue-400 px-2 py-1 rounded transition-colors truncate max-w-[200px] border border-slate-700"
                  >
                    <ExternalLink size={10} />
                    Source {idx + 1}
                  </a>
                ))}
                {!item.marketResearch?.compLinks.length && <span className="text-xs text-slate-600">No direct links provided.</span>}
              </div>
            </div>
            
             <div className="p-4 bg-slate-950 rounded border border-slate-800">
               <h3 className="text-sm font-semibold text-slate-400 mb-2">Original Description</h3>
               <p className="text-xs text-slate-500 leading-relaxed max-h-32 overflow-y-auto">{item.description}</p>
             </div>
          </div>

          {/* Right Column: AI Analysis */}
          <div className="space-y-6 flex flex-col h-full">
            <div className="bg-gradient-to-br from-slate-900 to-indigo-950/30 border border-indigo-900/50 p-5 rounded-lg">
               <div className="flex items-center gap-2 mb-3">
                 <ShieldAlert className="text-indigo-400" size={20} />
                 <h3 className="font-semibold text-indigo-200">Risk Assessment</h3>
               </div>
               <div className="text-sm text-indigo-300 mb-3">
                 Risk Score: <span className="font-bold">{item.profitAnalysis?.riskScore}/10</span>
               </div>
               <ul className="space-y-1">
                 {item.profitAnalysis?.riskFactors.map((risk, i) => (
                   <li key={i} className="flex items-start gap-2 text-xs text-indigo-300/80">
                     <span className="mt-0.5">•</span> {risk}
                   </li>
                 ))}
                 {!item.profitAnalysis?.riskFactors.length && <li className="text-xs text-indigo-500">No major risks identified.</li>}
               </ul>
            </div>

            <div className="flex-1 flex flex-col border border-slate-800 rounded-lg p-5 bg-slate-900">
              <div className="flex items-center justify-between mb-4">
                 <div className="flex items-center gap-2">
                   <BrainCircuit className="text-purple-400" size={20} />
                   <h3 className="font-semibold text-slate-200">Deep AI Analysis</h3>
                 </div>
                 {!item.deepAnalysis && (
                   <button 
                    onClick={handleDeepAnalysis}
                    disabled={isThinking}
                    className="text-xs bg-purple-600 hover:bg-purple-700 text-white px-3 py-1.5 rounded-md transition-all flex items-center gap-2 disabled:opacity-50 shadow-md shadow-purple-900/20"
                   >
                     {isThinking ? 'Thinking...' : 'Run Deep Scan'}
                   </button>
                 )}
              </div>
              
              <div className="flex-1 overflow-y-auto bg-slate-950 rounded p-4 text-sm text-slate-300 leading-relaxed min-h-[200px] border border-slate-800 custom-scrollbar">
                {isThinking ? (
                  <div className="flex flex-col items-center justify-center h-full text-slate-500 gap-3">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-500"></div>
                    <p className="text-xs">Analyzing market saturation, shipping risks, and hidden costs...</p>
                  </div>
                ) : item.deepAnalysis ? (
                  <div className="whitespace-pre-wrap">{item.deepAnalysis}</div>
                ) : (
                  <div className="text-center text-slate-600 h-full flex items-center justify-center p-4">
                    <p>Click "Run Deep Scan" to use the Gemini Thinking model for a comprehensive risk report.</p>
                  </div>
                )}
              </div>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
};

export default ItemDetailModal;