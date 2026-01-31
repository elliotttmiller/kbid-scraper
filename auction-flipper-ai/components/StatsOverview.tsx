import React from 'react';
import { AnalyzedItem } from '../types';
import { DollarSign, Percent, ShoppingCart, Activity } from 'lucide-react';

const StatCard: React.FC<{ title: string; value: string; icon: React.ReactNode; color: string; textColor: string }> = ({ title, value, icon, color, textColor }) => (
  <div className="bg-slate-900 p-6 rounded-lg shadow-sm border border-slate-800 flex items-center gap-4">
    <div className={`p-3 rounded-full ${color}`}>
      {icon}
    </div>
    <div>
      <p className="text-sm text-slate-400 font-medium">{title}</p>
      <h3 className={`text-2xl font-bold ${textColor}`}>{value}</h3>
    </div>
  </div>
);

interface StatsOverviewProps {
  items: AnalyzedItem[];
}

const StatsOverview: React.FC<StatsOverviewProps> = ({ items }) => {
  const analyzedItems = items.filter(i => i.status === 'complete' && i.profitAnalysis);
  
  const totalProfit = analyzedItems.reduce((acc, i) => acc + (i.profitAnalysis?.netProfit || 0), 0);
  const avgRoi = analyzedItems.length > 0 
    ? analyzedItems.reduce((acc, i) => acc + (i.profitAnalysis?.roi || 0), 0) / analyzedItems.length
    : 0;
  
  const strongBuys = analyzedItems.filter(i => i.profitAnalysis?.recommendation === 'STRONG BUY').length;
  const buys = analyzedItems.filter(i => i.profitAnalysis?.recommendation === 'BUY').length;

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      <StatCard 
        title="Total Potential Profit" 
        value={`$${totalProfit.toFixed(2)}`} 
        icon={<DollarSign size={24} className="text-green-400" />} 
        color="bg-green-900/30"
        textColor="text-green-400"
      />
      <StatCard 
        title="Average ROI" 
        value={`${avgRoi.toFixed(1)}%`} 
        icon={<Percent size={24} className="text-cyan-400" />} 
        color="bg-cyan-900/30"
        textColor="text-cyan-400"
      />
      <StatCard 
        title="Opportunities (Buy+)" 
        value={`${strongBuys + buys}`} 
        icon={<ShoppingCart size={24} className="text-purple-400" />} 
        color="bg-purple-900/30"
        textColor="text-purple-400"
      />
      <StatCard 
        title="Analyzed Items" 
        value={`${analyzedItems.length} / ${items.length}`} 
        icon={<Activity size={24} className="text-blue-400" />} 
        color="bg-blue-900/30"
        textColor="text-blue-400"
      />
    </div>
  );
};

export default StatsOverview;