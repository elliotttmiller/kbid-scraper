# Project Structure

## Root Layout
```
kbid-scraper/
├── auction-flipper-ai/   # React/TS frontend with AI analysis
├── kbid-scraper/         # Python scraper backend
├── market-analyzer/      # Python market analysis scripts
├── results/              # Scraper output CSVs and logs
└── README.md
```

## auction-flipper-ai/
```
├── components/
│   ├── AnalysisTable.tsx     # Sortable table of analyzed items
│   ├── AuctionGroupCard.tsx  # Card view per auction group
│   ├── ChatBot.tsx           # Gemini-powered chat interface
│   ├── FileUpload.tsx        # CSV drag-and-drop upload
│   ├── ItemDetailModal.tsx   # Per-item deep analysis modal
│   └── StatsOverview.tsx     # Aggregate stats dashboard
├── services/
│   ├── aiLimiter.ts          # Bottleneck rate limiter for Gemini
│   ├── analysis.ts           # Core AI analysis orchestration
│   ├── geminiService.ts      # Gemini API client wrapper
│   └── sourceAdapters.ts     # CSV parsing / data normalization
├── App.tsx                   # Root component, state management
├── constants.ts              # App-wide constants and defaults
├── index.tsx                 # Entry point
├── types.ts                  # Shared TypeScript interfaces
└── vite.config.ts            # Vite build config
```

## kbid-scraper/
```
├── scripts/
│   ├── run_auctions_test.py    # Test runner for scraper
│   └── advanced_examples.py   # Advanced usage examples
├── scraper_enhanced.py         # Main scraper implementation
└── requirements.txt
```

## market-analyzer/
```
├── auction_analyzer.py           # Core analyzer
├── auction_profit_analyzer.py    # Profit-focused analysis
├── gemini_auction_analyzer.py    # Gemini-integrated analyzer
├── config.py                     # Configuration
├── demo.py / demo_gemini_analyzer.py  # Demo scripts
└── *.md                          # Guides and documentation
```

## Architectural Patterns
- Separation of concerns: scraper (data collection) → CSV → frontend (AI analysis)
- Services layer in frontend isolates AI/API logic from UI components
- Shared types.ts defines all domain models used across components and services
- Rate limiting is centralized in aiLimiter.ts, consumed by analysis.ts
- No backend server for the frontend — runs entirely client-side with direct Gemini API calls
