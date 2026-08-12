# Local Development Setup Guide

## Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| Node.js | 18+ | Frontend dev server and build |
| Python | 3.7+ | Scraper and market analyzer |
| Git | any | Source control |
| VS Code | any | Recommended IDE |

---

## 1. Clone & Open in VS Code

```powershell
git clone <repo-url>
cd kbid-scraper
code .
```

---

## 2. Environment Variables

The frontend requires a Gemini API key. Get one free at https://aistudio.google.com/apikey.

Create `auction-flipper-ai/.env.local`:
```
GEMINI_API_KEY=your_api_key_here
```

> The market-analyzer Python scripts read `GOOGLE_API_KEY` from the environment instead:
> ```powershell
> $env:GOOGLE_API_KEY = "your_api_key_here"
> ```

---

## 3. Frontend — auction-flipper-ai

```powershell
cd auction-flipper-ai
npm install
npm run dev
```

App runs at **http://localhost:3000**

Other commands:
```powershell
npm run build    # Production build → dist/
npm run preview  # Serve the production build locally
```

---

## 4. Python Scraper — kbid-scraper

```powershell
cd kbid-scraper
pip install -r requirements.txt
```

### Run a test scrape (first 5 auctions)
```powershell
python scripts\run_auctions_test.py --num-auctions 5 --delay 1 --output test_auctions.csv
```

### Run advanced examples
```powershell
python scripts\advanced_examples.py
```

### Run the full interactive scraper
```powershell
python scraper_enhanced.py
```

Output CSVs are written to `../results/run_<timestamp>/`.
The shared log file is at `../results/kbid_scraper.log`.

---

## 5. Market Analyzer — market-analyzer

```powershell
cd market-analyzer
pip install -r requirements.txt

# Demo (no API key needed)
python demo.py

# Gemini-powered analysis (requires GOOGLE_API_KEY)
python demo_gemini_analyzer.py

# Full profit analyzer against a CSV
python auction_profit_analyzer.py
```

---

## 6. End-to-End Workflow

```
1. Run scraper  →  results/run_<timestamp>/test_auctions.csv
2. Open frontend at http://localhost:3000
3. Upload the CSV via the FileUpload component
4. Frontend calls Gemini AI to analyze each item
5. Review results in the auction group cards and analysis table
```

---

## 7. VS Code Recommended Extensions

Install these for the best experience:

- **ESLint** (`dbaeumer.vscode-eslint`) — TypeScript linting
- **Prettier** (`esbenp.prettier-vscode`) — Code formatting
- **Python** (`ms-python.python`) — Python language support
- **Pylance** (`ms-python.vscode-pylance`) — Python type checking
- **Vite** (`antfu.vite`) — Vite integration

### Suggested workspace settings (`.vscode/settings.json`)
```json
{
  "editor.formatOnSave": true,
  "editor.defaultFormatter": "esbenp.prettier-vscode",
  "[python]": {
    "editor.defaultFormatter": "ms-python.python"
  },
  "python.defaultInterpreterPath": "${workspaceFolder}/kbid-scraper/.venv/Scripts/python.exe"
}
```

---

## 8. Recommended: Python Virtual Environment

Using a venv keeps dependencies isolated:

```powershell
# From repo root
python -m venv .venv
.venv\Scripts\Activate.ps1

# Install all Python deps
pip install -r kbid-scraper\requirements.txt
pip install -r market-analyzer\requirements.txt
```

---

## 9. Troubleshooting

| Problem | Fix |
|---|---|
| `npm run dev` fails | Run `npm install` first inside `auction-flipper-ai/` |
| Gemini API errors in frontend | Check `GEMINI_API_KEY` is set in `.env.local` |
| `No module named 'requests'` | Run `pip install -r requirements.txt` in `kbid-scraper/` |
| `No module named 'google.generativeai'` | Run `pip install -r requirements.txt` in `market-analyzer/` |
| Scraper returns no data | Check internet connection; k-bid.com may have changed HTML structure |
| Port 3000 already in use | Kill the process or change `port` in `auction-flipper-ai/vite.config.ts` |
| PowerShell execution policy error | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
