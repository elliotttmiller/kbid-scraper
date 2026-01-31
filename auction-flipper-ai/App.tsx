import React, { useState, useRef, useMemo } from 'react';
import { AnalyzedItem, AuctionItem, AuctionGroupSummary } from './types';
import { quickScanItems, batchResearchItems, quickScanItem, researchItemMarket } from './services/geminiService';
import { calculateProfitability } from './services/analysis';
import { DEFAULT_SETTINGS } from './constants';
import FileUpload from './components/FileUpload';
import AnalysisTable from './components/AnalysisTable';
import StatsOverview from './components/StatsOverview';
import ItemDetailModal from './components/ItemDetailModal';
import ChatBot from './components/ChatBot';
import AuctionGroupCard from './components/AuctionGroupCard';
import { Gavel, PlayCircle, Loader, ChevronLeft, LayoutGrid, Layers, Square, PauseCircle } from 'lucide-react';

const App: React.FC = () => {
  // Master List of all items from all auctions
  const [items, setItems] = useState<AnalyzedItem[]>([]);
  const [selectedItem, setSelectedItem] = useState<AnalyzedItem | null>(null);
  
  // View State
  const [activeGroup, setActiveGroup] = useState<string | null>(null); // If null, show dashboard groups
  const [isBulkAnalyzing, setIsBulkAnalyzing] = useState(false);
  
  // Ref to track analysis status and allow cancellation
  const isAnalyzingRef = useRef(false);

  // --- Derived State: Group Aggregation ---
  const auctionGroups = useMemo(() => {
    const groups: Record<string, AuctionGroupSummary> = {};

    items.forEach(item => {
      if (!groups[item.groupName]) {
        groups[item.groupName] = {
          groupName: item.groupName,
          totalItems: 0,
          analyzedCount: 0,
          totalProfit: 0,
          avgRoi: 0,
          bestItem: undefined,
          status: 'pending',
          coverImage: item.imageUrl, // Use first item's image as cover
          location: item.location
        };
      }

      const g = groups[item.groupName];
      g.totalItems++;
      
      // Update status to processing if any item is analyzing
      if (item.status === 'analyzing') g.status = 'processing';

      if (item.status === 'complete' && item.profitAnalysis) {
        g.analyzedCount++;
        g.totalProfit += item.profitAnalysis.netProfit;
        
        // Update best item
        if (!g.bestItem || (item.profitAnalysis.netProfit > (g.bestItem.profitAnalysis?.netProfit || 0))) {
          g.bestItem = item;
        }
      }
    });

    // Finalize Averages and Status
    return Object.values(groups).map(g => {
      const groupItems = items.filter(i => i.groupName === g.groupName && i.status === 'complete');
      if (groupItems.length > 0) {
        const totalRoi = groupItems.reduce((acc, i) => acc + (i.profitAnalysis?.roi || 0), 0);
        g.avgRoi = totalRoi / groupItems.length;
        g.status = g.analyzedCount === g.totalItems ? 'complete' : g.status;
      }
      return g;
    });
  }, [items]);

  // Handle new data from CSV
  const handleDataLoaded = async (newItems: AuctionItem[]) => {
    const initialAnalyzed: AnalyzedItem[] = newItems.map(item => ({
      ...item,
      status: 'pending'
    }));
    // Append to existing, don't overwrite
    setItems(prev => [...prev, ...initialAnalyzed]);
  };

  // Analyze a single item
  const analyzeItem = async (item: AnalyzedItem) => {
    // Mark as analyzing in UI
    setItems(prev => prev.map(i => i.id === item.id ? { ...i, status: 'analyzing' } : i));
    
    try {
      // 1. Quick Scan
      let currentItem = { ...item };
      // Only run quick scan if we really need it, otherwise trust the prompt injection in market research
      if (currentItem.category === 'Uncategorized' || !currentItem.condition || currentItem.condition === 'Used') {
         const quickData = await quickScanItem(currentItem);
         currentItem.category = quickData.category !== 'Unknown' && quickData.category ? quickData.category : currentItem.category;
         currentItem.condition = quickData.condition !== 'Unknown' && quickData.condition ? quickData.condition : currentItem.condition;
      }

      // 2. Research
      const research = await researchItemMarket(currentItem);
      
      // 3. Profit Calc
      const profitAnalysis = calculateProfitability(currentItem, research, DEFAULT_SETTINGS);

      setItems(prev => prev.map(i => i.id === item.id ? { 
        ...currentItem, 
        marketResearch: research,
        profitAnalysis,
        status: 'complete' 
      } : i));

    } catch (error) {
      console.error(`Error analyzing item ${item.lotNumber}:`, error);
      setItems(prev => prev.map(i => i.id === item.id ? { ...i, status: 'error', error: 'Analysis Failed' } : i));
    }
  };

  // Bulk Analyze with Batch Processing
  const handleBulkAnalyze = async () => {
    // If already analyzing, this button acts as a stop button
    if (isBulkAnalyzing) {
        isAnalyzingRef.current = false;
        setIsBulkAnalyzing(false);
        return;
    }

    setIsBulkAnalyzing(true);
    isAnalyzingRef.current = true;
    
    // Filter items based on view
    const targetItems = activeGroup 
      ? items.filter(i => i.groupName === activeGroup && i.status === 'pending')
      : items.filter(i => i.status === 'pending');
    
    // Config: batch processing - run quickScan and lightweight market research in batches
    const BATCH_SIZE = 10; // number of items per LLM batch - tune for tokens/timeouts
    const BATCH_DELAY = 1000;

    for (let i = 0; i < targetItems.length; i += BATCH_SIZE) {
      if (!isAnalyzingRef.current) break; // Check for cancellation

      const batch = targetItems.slice(i, i + BATCH_SIZE);

      // Mark batch items as analyzing in UI
      setItems(prev => prev.map(it => batch.find(b => b.id === it.id) ? { ...it, status: 'analyzing' } : it));

      // Prepare AuctionItem-shaped payloads
      const payload = batch.map(b => ({
        id: b.id,
        lotNumber: b.lotNumber,
        title: b.title,
        groupName: b.groupName,
        description: b.description,
        currentBid: b.currentBid,
        category: b.category,
        condition: b.condition,
        shippingCost: b.shippingCost,
        imageUrl: b.imageUrl,
        itemUrl: b.itemUrl,
        location: b.location
      }));

      try {
        // 1) Batch quick-scan (N -> 1 call)
        const quickResults = await quickScanItems(payload);
        quickResults.forEach((qr, idx) => {
          if (qr && qr.category && qr.category !== 'Unknown') batch[idx].category = qr.category;
          if (qr && qr.condition && qr.condition !== 'Unknown') batch[idx].condition = qr.condition;
        });

        // 2) Lightweight batch market research (no web grounding) - cheaper
        const marketResults = await batchResearchItems(payload, false);

        // 3) Compute profit analysis and update items
        const updatedItems = batch.map((orig, idx) => {
          const research = marketResults[idx];
          const profitAnalysis = calculateProfitability(orig as any, research as any, DEFAULT_SETTINGS);
          return { ...orig, marketResearch: research, profitAnalysis, status: 'complete' } as AnalyzedItem;
        });

        // Apply updates to global state
        setItems(prev => prev.map(it => {
          const u = updatedItems.find(ui => ui.id === it.id);
          return u ? { ...it, ...u } : it;
        }));

      } catch (err) {
        console.error('Batch analysis error:', err);
        // Fallback: analyze items individually (safer)
        await Promise.all(batch.map(item => analyzeItem(item)));
      }

      // Rate limiting delay between batches
      if (i + BATCH_SIZE < targetItems.length && isAnalyzingRef.current) {
         await new Promise(r => setTimeout(r, BATCH_DELAY));
      }
    }
    
    setIsBulkAnalyzing(false);
    isAnalyzingRef.current = false;
  };

  const filteredItems = activeGroup 
    ? items.filter(i => i.groupName === activeGroup)
    : items;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 pb-24">
      {/* Navbar */}
      <header className="bg-slate-900 border-b border-slate-800 sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2 cursor-pointer" onClick={() => setActiveGroup(null)}>
            <div className="bg-blue-500 p-2 rounded-lg text-slate-900 shadow-[0_0_15px_rgba(59,130,246,0.3)]">
              <Gavel size={20} strokeWidth={2.5} />
            </div>
            <span className="text-xl font-bold text-slate-100 tracking-tight">
              Auction<span className="text-blue-400">Flipper</span>
            </span>
          </div>
          <div className="text-sm text-slate-400 font-medium">
            Powered by Gemini AI
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        
        {/* Navigation / Header */}
        <div className="flex flex-col md:flex-row md:justify-between md:items-center mb-8 gap-4">
          <div>
            {activeGroup ? (
              <div className="flex items-center gap-2">
                <button 
                  onClick={() => setActiveGroup(null)}
                  className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-white transition-colors"
                >
                  <ChevronLeft size={24} />
                </button>
                <div>
                  <h1 className="text-2xl font-bold text-slate-100 max-w-xl truncate" title={activeGroup}>{activeGroup}</h1>
                  <p className="text-slate-400 flex items-center gap-2">
                    <Layers size={14} /> Auction Lot Details
                  </p>
                </div>
              </div>
            ) : (
              <div>
                <h1 className="text-2xl font-bold text-slate-100">Dashboard</h1>
                <p className="text-slate-400">Manage your auction lots and inventory.</p>
              </div>
            )}
          </div>

          <div className="flex gap-3">
             {(filteredItems.some(i => i.status === 'pending') || isBulkAnalyzing) && (
               <button 
                onClick={handleBulkAnalyze}
                className={`
                    px-4 py-2 rounded-lg flex items-center gap-2 font-medium transition-all shadow-sm border
                    ${isBulkAnalyzing 
                        ? 'bg-amber-600 hover:bg-amber-500 border-amber-700 text-white' 
                        : 'bg-blue-600 hover:bg-blue-500 border-blue-700 text-white'}
                `}
               >
                 {isBulkAnalyzing ? (
                    <>
                        <PauseCircle size={18} className="animate-pulse" />
                        Stop Processing
                    </>
                 ) : (
                    <>
                        <PlayCircle size={18} />
                        Analyze {activeGroup ? 'Lot' : 'All'} Pending
                    </>
                 )}
               </button>
             )}
          </div>
        </div>

        {/* View Logic */}
        {!activeGroup && items.length === 0 ? (
          // Empty State
          <div className="max-w-2xl mx-auto mt-20">
            <FileUpload onDataLoaded={handleDataLoaded} />
            <div className="mt-8 text-center">
               <p className="text-slate-500 text-sm mb-4">Don't have a CSV?</p>
               <button 
                 onClick={() => handleDataLoaded([
                   { id: '1', lotNumber: '101', title: 'Sony WH-1000XM5', groupName: 'Electronics Liquidation - Jan', description: 'Open box', currentBid: 120.00, category: 'Electronics', condition: 'Open Box', imageUrl: 'https://images.unsplash.com/photo-1618366712010-f4ae9c647dcb?auto=format&fit=crop&q=80&w=200', location: 'New York, NY' },
                   { id: '2', lotNumber: '102', title: 'Dyson V15', groupName: 'Electronics Liquidation - Jan', description: 'Used', currentBid: 250.00, category: 'Home', condition: 'Used', imageUrl: 'https://images.unsplash.com/photo-1558317374-a3545eca640e?auto=format&fit=crop&q=80&w=200', location: 'Austin, TX' },
                   { id: '3', lotNumber: '103', title: 'Aeron Chair', groupName: 'Office Surplus #44', description: 'Damaged', currentBid: 300.00, category: 'Furniture', condition: 'Damaged', location: 'Seattle, WA' },
                 ])}
                 className="text-blue-400 font-medium hover:text-blue-300 underline decoration-blue-500/30 underline-offset-4"
               >
                 Load Demo Data
               </button>
            </div>
          </div>
        ) : !activeGroup ? (
          // Dashboard View: Show Auction Groups
          <div className="space-y-8">
            <StatsOverview items={items} />
            
            <div>
              <div className="flex items-center gap-2 mb-4 text-slate-300">
                <LayoutGrid size={18} />
                <h2 className="font-semibold">Auction Lots ({auctionGroups.length})</h2>
              </div>
              
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {auctionGroups.map(group => (
                  <AuctionGroupCard 
                    key={group.groupName} 
                    group={group} 
                    onClick={() => setActiveGroup(group.groupName)} 
                  />
                ))}
                 {/* Mini Dropzone for adding more lots */}
                 <div className="border-2 border-dashed border-slate-800 rounded-xl flex flex-col items-center justify-center p-6 hover:bg-slate-900/50 hover:border-slate-700 transition-colors cursor-pointer min-h-[200px]">
                    <FileUpload onDataLoaded={handleDataLoaded} />
                 </div>
              </div>
            </div>
          </div>
        ) : (
          // Detail View: Show Items for specific group
          <div className="space-y-6">
            <StatsOverview items={filteredItems} />
            <AnalysisTable 
              items={filteredItems} 
              onAnalyze={analyzeItem} 
              onViewDetails={setSelectedItem} 
            />
          </div>
        )}
      </main>

      {selectedItem && (
        <ItemDetailModal 
          item={selectedItem} 
          onClose={() => setSelectedItem(null)}
          onUpdateItem={(updated) => {
             setItems(prev => prev.map(i => i.id === updated.id ? updated : i));
             setSelectedItem(updated);
          }}
        />
      )}

      {items.length > 0 && <ChatBot analyzedItems={items} />}

    </div>
  );
};

export default App;