import React from 'react';
import { AnalyzedItem } from '../types';
import { ExternalLink, TrendingUp, AlertTriangle, CheckCircle, XCircle, ImageIcon } from 'lucide-react';

interface AnalysisTableProps {
  items: AnalyzedItem[];
  onAnalyze: (item: AnalyzedItem) => void;
  onViewDetails: (item: AnalyzedItem) => void;
}

const AnalysisTable: React.FC<AnalysisTableProps> = ({ items, onAnalyze, onViewDetails }) => {
  
  const getScoreColor = (score: number) => {
    if (score >= 70) return 'text-green-400 bg-green-500/10 border border-green-500/20';
    if (score >= 50) return 'text-blue-400 bg-blue-500/10 border border-blue-500/20';
    if (score >= 30) return 'text-amber-400 bg-amber-500/10 border border-amber-500/20';
    return 'text-red-400 bg-red-500/10 border border-red-500/20';
  };

  const getRecommendationBadge = (rec: string) => {
    switch (rec) {
      case 'STRONG BUY': return <span className="px-2 py-1 rounded text-xs font-bold bg-green-900/50 text-green-400 border border-green-800">Strong</span>;
      case 'BUY': return <span className="px-2 py-1 rounded text-xs font-bold bg-blue-900/50 text-blue-400 border border-blue-800">Good</span>;
      case 'MAYBE': return <span className="px-2 py-1 rounded text-xs font-bold bg-amber-900/50 text-amber-400 border border-amber-800">Fair</span>;
      default: return <span className="px-2 py-1 rounded text-xs font-bold bg-slate-800 text-slate-400 border border-slate-700">Pass</span>;
    }
  };

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-800 shadow-sm bg-slate-900">
      <table className="w-full text-sm text-left text-slate-400">
        <thead className="text-xs text-slate-400 uppercase bg-slate-800/50 border-b border-slate-800">
          <tr>
            <th className="px-6 py-3 w-16">Image</th>
            <th className="px-6 py-3">Lot #</th>
            <th className="px-6 py-3">Item</th>
            <th className="px-6 py-3">Bid</th>
            <th className="px-6 py-3">Est. Value</th>
            <th className="px-6 py-3">Net Profit</th>
            <th className="px-6 py-3">ROI</th>
            <th className="px-6 py-3">Score</th>
            <th className="px-6 py-3">Status</th>
            <th className="px-6 py-3">Action</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id} className="bg-slate-900 border-b border-slate-800 hover:bg-slate-800/50 transition-colors">
              <td className="px-6 py-4">
                <div className="w-12 h-12 rounded bg-slate-800 overflow-hidden flex items-center justify-center border border-slate-700">
                  {item.imageUrl ? (
                    <img src={item.imageUrl} alt={item.title} className="w-full h-full object-cover" />
                  ) : (
                    <ImageIcon size={20} className="text-slate-600" />
                  )}
                </div>
              </td>
              <td className="px-6 py-4 font-medium text-slate-300">{item.lotNumber}</td>
              <td className="px-6 py-4 max-w-xs">
                <div className="flex items-start gap-2">
                   <div className="font-semibold text-slate-200 truncate max-w-[200px]" title={item.title}>{item.title}</div>
                   {item.itemUrl && (
                     <a href={item.itemUrl} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:text-blue-300 mt-0.5">
                       <ExternalLink size={12} />
                     </a>
                   )}
                </div>
                <div className="text-xs text-slate-500 truncate">{item.location || item.category} • {item.condition}</div>
              </td>
              <td className="px-6 py-4 font-medium text-slate-200">${item.currentBid.toFixed(2)}</td>
              <td className="px-6 py-4 text-slate-300">
                {item.profitAnalysis ? (
                  `$${item.profitAnalysis.estimatedSellPrice.toFixed(2)}`
                ) : (
                  <span className="text-slate-600">-</span>
                )}
              </td>
              <td className="px-6 py-4">
                {item.profitAnalysis ? (
                  <span className={item.profitAnalysis.netProfit > 0 ? 'text-green-400 font-medium' : 'text-red-400'}>
                    ${item.profitAnalysis.netProfit.toFixed(2)}
                  </span>
                ) : (
                  <span className="text-slate-600">-</span>
                )}
              </td>
              <td className="px-6 py-4">
                {item.profitAnalysis ? (
                   <span className={item.profitAnalysis.roi > 20 ? 'text-green-400' : 'text-slate-400'}>
                     {item.profitAnalysis.roi.toFixed(1)}%
                   </span>
                ) : (
                  <span className="text-slate-600">-</span>
                )}
              </td>
              <td className="px-6 py-4">
                {item.profitAnalysis ? (
                   <div className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-bold ${getScoreColor(item.profitAnalysis.opportunityScore)}`}>
                     {Math.round(item.profitAnalysis.opportunityScore)}
                   </div>
                ) : (
                  <span className="text-slate-600">-</span>
                )}
              </td>
              <td className="px-6 py-4">
                {item.status === 'pending' && <span className="text-slate-500 text-xs">Pending</span>}
                {item.status === 'analyzing' && <span className="text-blue-400 text-xs animate-pulse">Researching...</span>}
                {item.status === 'complete' && item.profitAnalysis && getRecommendationBadge(item.profitAnalysis.recommendation)}
                {item.status === 'error' && <span className="text-red-400 text-xs">Error</span>}
              </td>
              <td className="px-6 py-4">
                <div className="flex items-center gap-2">
                  {item.status === 'pending' || item.status === 'error' ? (
                    <button 
                      onClick={() => onAnalyze(item)}
                      className="p-1.5 text-blue-500 hover:bg-blue-500/10 rounded transition-colors"
                      title="Analyze Item"
                    >
                      <TrendingUp size={16} />
                    </button>
                  ) : (
                    <button 
                       onClick={() => onViewDetails(item)}
                       className="p-1.5 text-slate-400 hover:bg-slate-700 rounded transition-colors"
                       title="View Details"
                    >
                      <ExternalLink size={16} />
                    </button>
                  )}
                </div>
              </td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr>
              <td colSpan={10} className="text-center py-10 text-slate-500">
                No items loaded. Upload a CSV to begin.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
};

export default AnalysisTable;