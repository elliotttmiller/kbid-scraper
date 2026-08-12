# Legacy Market Analyzer Prototypes

These files are retained for historical comparison only. They contain the original experimental Gemini prompts and duplicate cost models; they are not wired into the production workflow and should not be used for bidding decisions.

Use the canonical root commands instead:

```powershell
python .\analyze_auctions.py .\path\to\scraper.csv --ebay --gemini-research
python .\serve_engine.py
```

The production implementation lives in `../auction_engine/`, with configuration in `../engine_config.json`. It requires traceable evidence, calculates all costs deterministically, emits maximum bids and scenario EV, caches research, and keeps provider keys out of the browser.
