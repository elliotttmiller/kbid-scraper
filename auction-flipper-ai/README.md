# Auction Flipper Dashboard

The dashboard is a thin client for the canonical Python valuation engine. It does not contain market-provider credentials or independent profit math.

```powershell
# From the repository root
python .\serve_engine.py

# In another terminal
cd .\auction-flipper-ai
npm install
npm run dev
```

The API defaults to `http://127.0.0.1:8000`. Set `VITE_AUCTION_API_URL` only when the backend runs elsewhere. Configure eBay and Gemini credentials on the backend process, never in a Vite environment variable.
