import React, { useRef } from 'react';
import Papa from 'papaparse';
import { Upload, FileText, FolderPlus } from 'lucide-react';
import { AuctionItem } from '../types';

interface FileUploadProps {
  onDataLoaded: (items: AuctionItem[]) => void;
}

const FileUpload: React.FC<FileUploadProps> = ({ onDataLoaded }) => {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      parseCSV(file);
    }
  };

  const cleanTitle = (rawTitle: string, description: string, location: string = ''): string => {
    // If title looks like an auction event name (long, contains "Auction"), 
    // or specifically matches the pattern where title is not the item name.
    const isGenericTitle = rawTitle.includes('Auction') || rawTitle.length > 60;
    
    if (isGenericTitle && description) {
      // Heuristic: "Item Name located in City, State"
      // Use the provided location field to make the split more accurate
      const splitKey = location ? ` located in ${location}` : ' located in ';
      
      if (description.includes(splitKey)) {
        return description.split(splitKey)[0].trim();
      }
      
      // Fallback split if location not found but "located in" exists
      const fallbackSplit = description.split(' located in ');
      if (fallbackSplit.length > 1) {
        return fallbackSplit[0].trim();
      }
      
      // If description is short, use it as title
      if (description.length < 100) return description;
    }
    return rawTitle;
  };

  const parseCSV = (file: File) => {
    Papa.parse(file, {
      header: true,
      skipEmptyLines: true,
      complete: (results) => {
        const defaultGroupName = `Upload ${new Date().toLocaleDateString()}`;
        
        const parsedItems: AuctionItem[] = results.data.map((row: any, index) => {
          // Explicit mapping based on user specifications:
          // 'lot_number', 'auction_title', 'item_title', 'short_description', 
          // 'current_bid', 'next_required_bid', 'high_bidder', 
          // 'item_closing_time', 'closing_date', 'item_url', 
          // 'auction_id', 'auction_url', 'location'

          const lotNumber = row['lot_number'] || String(index + 1);
          
          // Grouping: Use 'auction_title'
          const groupName = row['auction_title'] || defaultGroupName;
          
          // Title Processing
          const rawTitle = row['item_title'] || 'Untitled Item';
          const description = row['short_description'] || '';
          const location = row['location']; // Used for cleaning title
          
          // Special handling: Some scrapers put the Auction Title in the item_title column
          const finalTitle = (rawTitle === groupName || rawTitle.includes('Consignment Auction'))
            ? cleanTitle(rawTitle, description, location)
            : cleanTitle(rawTitle, description, location);

          // Pricing
          const bidRaw = row['current_bid'] || '0';
          const currentBid = parseFloat(String(bidRaw).replace(/[^0-9.]/g, ''));

          // URLs & Metadata
          const itemUrl = row['item_url'] || row['auction_url'];
          // Note: image_url might be present in file even if not in the minimal header list
          const imageUrl = row['image_url'] || row['image']; 
          
          return {
            id: `item-${lotNumber}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
            lotNumber: lotNumber,
            title: finalTitle,
            groupName: groupName,
            description: description,
            currentBid: isNaN(currentBid) ? 0 : currentBid,
            category: row['category'] || row['categories'] || 'Uncategorized',
            condition: row['condition'] || 'Used',
            shippingCost: 0, // Default to 0, analysis will apply default shipping setting
            imageUrl: imageUrl,
            itemUrl: itemUrl,
            location: location || ''
          };
        });

        // Basic validation to remove empty rows
        const validItems = parsedItems.filter(item => item.title && item.title !== 'Untitled Item');
        onDataLoaded(validItems);
      },
      error: (error) => {
        console.error("CSV Parse Error:", error);
        alert("Failed to parse CSV. Please check the format.");
      }
    });
  };

  return (
    <div 
      className="border-2 border-dashed border-slate-700 bg-slate-900/50 rounded-lg p-10 text-center hover:bg-slate-900 hover:border-slate-600 transition-colors cursor-pointer group"
      onClick={() => fileInputRef.current?.click()}
    >
      <input 
        type="file" 
        ref={fileInputRef} 
        onChange={handleFileChange} 
        accept=".csv" 
        className="hidden" 
      />
      <div className="flex flex-col items-center gap-4">
        <div className="bg-slate-800 p-4 rounded-full text-blue-500 group-hover:scale-110 transition-transform">
          <FolderPlus size={32} />
        </div>
        <div>
          <h3 className="text-lg font-semibold text-slate-200">Import Auction Lots</h3>
          <p className="text-slate-500 text-sm mt-1">Drag and drop CSV (Auto-groups by 'auction_title')</p>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-600 mt-2">
          <FileText size={14} />
          <span>Supported format: .csv</span>
        </div>
      </div>
    </div>
  );
};

export default FileUpload;