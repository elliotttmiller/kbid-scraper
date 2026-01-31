import React from 'react';
import { AuctionGroupSummary } from '../types';
import { Package, TrendingUp, AlertCircle, ArrowRight, DollarSign } from 'lucide-react';

interface AuctionGroupCardProps {
  group: AuctionGroupSummary;
  onClick: () => void;
}

const AuctionGroupCard: React.FC<AuctionGroupCardProps> = ({ group, onClick }) => {
  const percentComplete = Math.round((group.analyzedCount / group.totalItems) * 100);

  return (
    <div 
      onClick={onClick}
      className="bg-slate-900 border border-slate-800 rounded-xl p-5 hover:border-blue-500/50 hover:bg-slate-800/80 transition-all cursor-pointer group relative overflow-hidden"
    >
      {/* Progress Bar Background */}
      <div className="absolute bottom-0 left-0 h-1 bg-slate-800 w-full">
        <div 
          className="h-full bg-blue-500 transition-all duration-500" 
          style={{ width: `${percentComplete}%` }}
        />
      </div>

      <div className="flex justify-between items-start mb-4">
        <div className="bg-slate-800 p-2.5 rounded-lg text-blue-500 border border-slate-700">
          <Package size={24} />
        </div>
        <div className="flex items-center gap-2">
          {group.status === 'processing' && (
            <span className="text-xs font-medium text-blue-400 flex items-center gap-1 animate-pulse">
              Processing...
            </span>
          )}
          <span className="text-xs font-medium text-slate-500 bg-slate-950 px-2 py-1 rounded-full border border-slate-800">
            {group.totalItems} Items
          </span>
        </div>
      </div>

      <h3 className="text-lg font-bold text-slate-100 mb-1 truncate" title={group.groupName}>
        {group.groupName}
      </h3>
      <div className="text-slate-500 text-xs mb-4 truncate">
         {group.location || 'Location Not Specified'}
      </div>

      <div className="grid grid-cols-2 gap-2 mb-4">
        <div className="bg-slate-950 p-2 rounded border border-slate-800">
          <p className="text-[10px] text-slate-500 uppercase font-bold">Pot. Profit</p>
          <p className={`text-sm font-bold ${group.totalProfit > 0 ? 'text-green-400' : 'text-slate-400'}`}>
            ${group.totalProfit.toFixed(0)}
          </p>
        </div>
        <div className="bg-slate-950 p-2 rounded border border-slate-800">
          <p className="text-[10px] text-slate-500 uppercase font-bold">Avg ROI</p>
          <p className={`text-sm font-bold ${group.avgRoi > 20 ? 'text-green-400' : 'text-slate-400'}`}>
            {group.avgRoi.toFixed(0)}%
          </p>
        </div>
      </div>

      {group.bestItem ? (
        <div className="flex items-center gap-2 text-xs text-slate-400 border-t border-slate-800 pt-3">
          <TrendingUp size={14} className="text-green-500" />
          <span className="truncate">Top: {group.bestItem.title}</span>
        </div>
      ) : (
        <div className="flex items-center gap-2 text-xs text-slate-500 border-t border-slate-800 pt-3">
          <AlertCircle size={14} />
          <span>Pending Analysis</span>
        </div>
      )}

      <div className="absolute top-5 right-5 opacity-0 group-hover:opacity-100 transition-opacity transform translate-x-2 group-hover:translate-x-0">
        <ArrowRight className="text-slate-400" size={20} />
      </div>
    </div>
  );
};

export default AuctionGroupCard;