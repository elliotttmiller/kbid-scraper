# Technology Stack

## auction-flipper-ai (Frontend)

### Languages & Runtime
- TypeScript ~5.8.2, target ES2022
- React 19.2.4 with react-jsx transform
- Node.js (dev tooling)

### Build
- Vite 6.2 with @vitejs/plugin-react
- ESM modules (`"type": "module"`)
- Path alias: `@/*` → project root

### Key Dependencies
| Package | Version | Purpose |
|---|---|---|
| @google/genai | ^1.38.0 | Gemini AI API client |
| bottleneck | ^2.19.5 | Rate limiting for API calls |
| papaparse | ^5.5.3 | CSV parsing |
| lucide-react | ^0.563.0 | Icon library |

### Dev Commands
```bash
cd auction-flipper-ai
npm install
npm run dev       # Start dev server
npm run build     # Production build
npm run preview   # Preview production build
```

### Environment
- Requires `GEMINI_API_KEY` (or `API_KEY`) environment variable / Vite env var for Gemini access

---

## kbid-scraper (Python Scraper)

### Language
- Python 3.x

### Dependencies
```
requests>=2.28.0
beautifulsoup4>=4.11.0
```

### Commands
```bash
cd kbid-scraper
pip install -r requirements.txt
python scripts/run_auctions_test.py
python scripts/advanced_examples.py
```

### Output
- CSV files written to `../results/run_<timestamp>/`
- Log file: `../results/kbid_scraper.log`

---

## market-analyzer (Python Analysis)

### Dependencies
```
google-generativeai>=0.8.0
```

### Commands
```bash
cd market-analyzer
pip install -r requirements.txt
python demo.py
python demo_gemini_analyzer.py
```

---

## TypeScript Config Highlights
- `moduleResolution: "bundler"` — Vite-compatible resolution
- `allowImportingTsExtensions: true` — import `.ts`/`.tsx` with extensions
- `noEmit: true` — type-check only, Vite handles transpilation
- `isolatedModules: true` — each file is independently compilable
