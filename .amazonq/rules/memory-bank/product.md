# Product Overview

## Purpose
A multi-module auction intelligence platform for scraping, analyzing, and flipping auction lots (primarily KBID/liquidation auctions). It combines a Python scraper backend with an AI-powered React frontend to identify profitable resale opportunities.

## Modules

### kbid-scraper (Python)
- Scrapes auction listings from KBID and similar liquidation platforms
- Outputs structured CSV data for downstream analysis
- Runs via CLI scripts with configurable test/production modes

### auction-flipper-ai (React/TypeScript)
- Uploads scraped CSV data for AI-driven profit analysis
- Uses Google Gemini AI to research market prices, estimate resale value, and score opportunities
- Displays results in grouped auction cards with sortable analysis tables
- Includes a ChatBot for conversational queries about analyzed lots
- Provides per-item deep analysis using Gemini's "thinking" model

### market-analyzer (Python)
- Standalone market analysis scripts and demos
- Integrates with Gemini API for auction profit analysis
- Provides reference implementations and guides for API integration

## Key Features
- CSV ingestion from scraper output or manual upload
- AI-powered market research (retail price, eBay sold avg, demand/liquidity scores)
- Profit analysis: net profit, ROI, opportunity score, buy recommendation (STRONG BUY / BUY / MAYBE / PASS)
- Rate-limited Gemini API calls via Bottleneck to avoid quota exhaustion
- Auction group summaries with best-item highlighting
- Configurable settings: shipping defaults, platform fee rate, min ROI/profit thresholds

## Target Users
Resellers and auction flippers who want to quickly evaluate liquidation lots for profitable resale on eBay or similar platforms.
