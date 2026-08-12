# K-Bid Auction Intelligence Engine

One pipeline discovers open K-Bid auctions, filters lots, collects traceable market evidence, and calculates risk-adjusted resale opportunities. Financial decisions are deterministic; AI is optional and limited to grounded online research.

`outputs/opportunities.csv` is a compact decision report containing only positive-profit candidates whose current bid remains below the calculated maximum bid. Complete analyzed rows, including `PASS` and negative-profit outcomes, plus cost assumptions, market ranges, evidence records, source URLs, and timestamps remain available in `outputs/opportunities.jsonl` and run metadata.

The report distinguishes verified sold evidence from active asking listings using separate count and median-price columns. Medians use delivered price (item price plus shipping) because they are more resistant than averages to extreme marketplace outliers. `expected_sell_price` remains the engine's risk-adjusted resale estimate. eBay Browse contributes current asking-price listings only; it is never represented as completed-sale evidence.

`ebay_active_listing_count` reports only traceable active results returned by the official eBay Browse provider. `active_listing_comp_count` is the total active evidence across all enabled providers, so the two values remain truthful after Gemini research is merged.

Opportunity rows and full JSONL analysis rows are ordered by the lot's closing time, soonest first. `lot_closing_time` is the absolute Central Time deadline and `time_remaining` records K-Bid's countdown snapshot when that lot was scraped. The CSV does not continuously update after the run.

For a cost-efficient second-stage Gemini pass, use `--candidate-csv` with the original raw lot CSV. Only prior opportunity URLs are analyzed, while complete raw auction costs and descriptions are retained. If candidates exceed the Gemini budget, selection prioritizes prior expected profit, closing urgency, confidence, and comparable counts.

Before grounded research, one non-grounded Gemini 3.1 Flash-Lite triage call audits at most 100 deterministic candidates and selects the top 50 available lots. It has no Google Search tool. Selection decisions and fallback status are written to `reports/gemini-triage.json`, with the polished ranked valuation list in `outputs/opportunities-triaged-top-50.csv`. That CSV and the grounded provider share the same selected item-ID allowlist, so grounded research executes only for those top-50 lots.

Grounded requests are audited per lot in `reports/gemini-grounded-research.jsonl`; the compact request, evidence, rejection, grounding-source, and token totals are written to `reports/gemini-grounded-summary.json`. A readable analyst report with per-lot outcomes, comparable prices, delivered prices, conditions, sold dates, and source links is written to `reports/gemini-grounded-report.md`. Sanitized response excerpts are capped at 4,000 characters, empty parsed responses are not cached, and a run is marked `partial_success` when grounded calls were attempted but yielded no usable cited evidence.

The primary human decision artifact is `reports/opportunity-analysis-report.md`. It combines every viable target's closing urgency, bid, modeled sale price, profit, ROI, maximum bid, confidence, sold and active evidence counts, recommendation, Gemini coverage, triage explanation, risk factors, and cited grounded comparables. The Gemini report remains an evidence appendix rather than the primary opportunity report.

Use `--gemini-triage-only` to run the Flash-Lite preprocessing stage after eBay valuation and stop without any grounded Gemini calls.

## Architecture

```text
K-Bid discovery -> auction/page/item workers -> sanitized scraper CSV
       -> category + open-lot gate -> evidence providers + SQLite cache
       -> scenario valuation / max bid / risk -> CSV + JSONL + React API
```

The canonical backend is `auction_engine/`. The older scripts under `market-analyzer/` are retained as reference prototypes and are not part of the production workflow.

## Results Layout

Every default run is self-contained and indexed by `results/latest.json`:

```text
results/
  runs/YYYY/MM/run_Ddd_DD_Mmm_YYYY_hh-mm-ss_-0600_<id>/
    raw/                         Scraped source CSVs
      lots.csv
    outputs/                     Machine-readable analysis outputs
      opportunities.csv
      opportunities.jsonl
    reports/                     Run summaries and future human reports
      run-summary.json
    logs/
      run.log                    INFO and above
      errors.log                 ERROR and above only
    state/
      scrape-checkpoint.json     Resume/checkpoint state
    metadata/
      manifest.json              Status, settings, counts, artifact map
      engine-config.json         Exact valuation configuration snapshot
  shared/cache/
    auction-engine.sqlite3       Reusable research and analysis cache
  latest.json                    Pointer to the newest run
```

Run names use an RFC 2822-style date, a 12-hour clock, and the Central Standard Time offset. The canonical display value remains unambiguous in metadata, such as `Tue, 11 Aug 2026 11:16:03 PM -0600`; the directory omits the AM/PM marker and becomes `run_Tue_11_Aug_2026_11-16-03_-0600_a1b2c3d4`. Use `--run-name` to record a recognizable label in metadata, `--results-root` to relocate the complete tree, and `--run-dir` with `--resume` to continue an existing run. Absolute output paths remain supported when an external system requires them.

## Install

```powershell
python -m pip install -r .\requirements.txt
python -m pip install -r .\kbid-scraper\requirements.txt
cd .\auction-flipper-ai
npm install
cd ..
```

Store local API credentials in `.env.local`. The Python engine loads that file automatically without overriding variables explicitly exported by PowerShell or the deployment environment. Both `.env.local` and `.env` are excluded from Git.

`ENABLE_GEMINI_RESEARCH=false` is a hard local safety gate. When set, Gemini remains disabled even if a command includes `--gemini-research`.

Optional research credentials are backend-only:

```powershell
$env:EBAY_CLIENT_ID='...'
$env:EBAY_CLIENT_SECRET='...'
$env:GEMINI_API_KEY='...'
```

## Full Pipeline

This discovers three auctions within 25 miles of `55447`, limits auction and lot timers to 72 hours, applies the profitability profile to lots, scrapes one auction at a time with parallel pages/items, then runs official eBay active-listing research and budgeted Gemini grounded research:

```powershell
python .\kbid-scraper\scripts\run_auctions_test.py --num-auctions 3 --category-profile profit-all-in-one --origin-zip 55447 --radius-miles 25 --listing-max-hours 72 --max-hours 72 --min-hours 0 --chunk-size 3 --auction-workers 1 --page-workers 3 --item-workers 8 --delay 1.0 --output profit_3_auctions.csv --analyze --ebay-research --gemini-research
```

Category filtering applies to lots by default. It does not filter auction discovery unless `--filter-listing-categories` is explicitly supplied.

Use `--all-auctions` to process every discovered auction that passes the listing filters. This explicit unlimited mode ignores `--num-auctions` while retaining the soonest-closing discovery order.

To analyze an existing scraper CSV:

```powershell
python .\analyze_auctions.py .\path\to\lots.csv --ebay --gemini-research
```

For highest-confidence pricing, provide analyst-verified sold comps:

```powershell
python .\analyze_auctions.py .\path\to\lots.csv --manual-comps .\manual_comps.example.csv --ebay --gemini-research
```

## Research Controls

- Gemini is opt-in and uses `gemini-2.5-flash` only for Google Search-grounded comparable discovery.
- It is skipped when manual or verified sold evidence already exists.
- No hard-coded dollar budget or request-spend ceiling stops Gemini workflows.
- A deterministic pre-screen favors identifiable, liquid, non-furniture lots; Gemini runs at two concurrent requests maximum.
- Output is capped at 1,200 tokens with one request per researched lot.
- AI output never performs profit math or makes the recommendation.
- Active asking prices are discounted and confidence-capped; they are never mislabeled as sold comps.

Tune premiums, tax, selling fees, labor, pickup, shipping, returns, minimum profit, target ROI, AI models, concurrency, shortlist sizing, and category exclusions in [engine_config.json](./engine_config.json).

## API And Dashboard

```powershell
python .\serve_engine.py
cd .\auction-flipper-ai
npm run dev
```

Open `http://localhost:3000`. The API defaults to `http://127.0.0.1:8000`; override it with `VITE_AUCTION_API_URL`. Enable backend Gemini research for the dashboard with `ENABLE_GEMINI_RESEARCH=true`.

Outputs include a ranked CSV and a full JSONL audit record containing assumptions, costs, scenarios, evidence URLs, confidence, risk factors, and maximum bid.
