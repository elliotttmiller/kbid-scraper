# Development Guidelines

## Code Quality Standards

### TypeScript
- Strict typing via shared `types.ts` — all domain models defined as interfaces, never inline
- Use generic functions for reusable async patterns: `limitedSchedule<T>(fn: () => Promise<T>): Promise<T>`
- Prefer named exports over default exports for services and utilities
- Guard against null DOM elements at entry point with explicit throws:
  ```ts
  if (!rootElement) throw new Error("Could not find root element to mount to");
  ```
- Use `React.StrictMode` in entry point

### Python
- Module-level docstrings on all scripts explaining purpose, usage, and notes
- Use `argparse` for all CLI scripts with sensible defaults and help strings
- Use `logging` (not `print`) with format `'%(asctime)s - %(levelname)s - %(message)s'`
- Guard `sys.path` manipulation with existence check before inserting
- Wrap file I/O in try/except with logger.error on failure — never silently swallow errors
- Use `if __name__ == '__main__': main()` pattern consistently

---

## Naming Conventions

### TypeScript
- Interfaces: PascalCase (`AuctionItem`, `ProfitAnalysis`, `AnalyzedItem`)
- Constants: SCREAMING_SNAKE_CASE (`DEFAULT_SETTINGS`, `MARKET_RESEARCH_SYSTEM_INSTRUCTION`)
- Services/files: camelCase (`aiLimiter.ts`, `geminiService.ts`, `sourceAdapters.ts`)
- Components: PascalCase filenames matching component name (`AnalysisTable.tsx`)

### Python
- Classes: PascalCase (`KBidScraperFixed`)
- Functions/variables: snake_case
- Constants/paths: SCREAMING_SNAKE_CASE (`SCRIPT_DIR`, `PROJECT_ROOT`)
- CLI args: kebab-case flags (`--num-auctions`, `--output`)

---

## Architectural Patterns

### Rate Limiting (Frontend)
All Gemini API calls go through the shared limiter — never call the API directly:
```ts
import { limitedSchedule } from '@/services/aiLimiter';
const result = await limitedSchedule(() => ai.models.generateContent(params));
```
Limiter config: `maxConcurrent: 2`, `minTime: 250ms` (~4 req/sec).

### AI Prompt Management
- All system instructions live in `constants.ts` as exported template strings
- Prompts are role-specific: market research, deep analysis, and chat each have their own instruction
- Instruct the model to return strict JSON where structured data is needed

### Environment / Config
- API keys injected at build time via Vite `define` — both `process.env.API_KEY` and `process.env.GEMINI_API_KEY` are mapped from `GEMINI_API_KEY` in `.env`
- Default user-configurable values (fees, thresholds) live in `DEFAULT_SETTINGS` in `constants.ts`

### CSV Streaming (Python)
- Write CSV header once on file open, then append rows per auction in a loop
- Use `extrasaction='ignore'` on `DictWriter` to handle extra fields gracefully
- Always use `encoding='utf-8'` and `newline=''` for CSV file handles

### Data Flow
```
Python scraper → CSV → FileUpload component → sourceAdapters (parse/normalize)
→ analysis service (Gemini via aiLimiter) → AnalyzedItem[] → UI components
```

---

## Structural Conventions

### Frontend Services
- One responsibility per service file: `aiLimiter` (throttling), `geminiService` (API client), `analysis` (orchestration), `sourceAdapters` (parsing)
- Services export pure functions or singleton instances — no classes

### Type Composition
- Extend base interfaces for enriched types: `AnalyzedItem extends AuctionItem`
- Use union string literals for status/recommendation fields:
  ```ts
  recommendation: 'STRONG BUY' | 'BUY' | 'MAYBE' | 'PASS'
  status: 'pending' | 'analyzing' | 'complete' | 'error'
  ```
- Optional fields use `?` — never `| undefined` explicitly

### Python Script Structure
1. Module docstring
2. Imports (stdlib → third-party → local)
3. `sys.path` setup for local imports
4. Logger setup at module level
5. `main()` function with argparse
6. `if __name__ == '__main__': main()`

---

## Comments & Documentation
- Inline comments explain *why*, not *what* (e.g., `// ~4 requests/sec`, `// ~13.5% generic eBay/PayPal average`)
- JSDoc-style block comments on exported utility functions
- Python scripts use module-level docstrings with Usage examples (PowerShell syntax for Windows)
- Avoid redundant comments that restate the code
