# AI Hedge Fund

Local **AI research** (default: **Ollama**) plus a **SQLite portfolio** with trades, corporate actions, and **value-weighted risk**. Stack: FastAPI, SQLAlchemy, React/Vite.

## LLM: free and open-source (recommended)

**[Ollama](https://ollama.com)** is the default: it runs open-weight models (Llama, Mistral, Qwen, etc.) on your machine — **no API keys**, **no usage fees**.

1. Install Ollama from the site above (macOS/Linux/Windows).
2. Pull a model (pick one you have or try a small one first):

   ```bash
   ollama pull llama3.2
   # or: ollama pull mistral / qwen2.5 / etc.
   ollama list
   ```

3. Ensure the daemon is up (usually automatic). If needed: `ollama serve`.
4. Point the app at your model in `.env`:

   ```bash
   cp .env.example .env
   # Set OLLAMA_MODEL to a name from `ollama list` (e.g. llama3.2, mistral, …)
   ```

5. Defaults: `LLM_PROVIDER=ollama`, `OLLAMA_BASE_URL=http://127.0.0.1:11434`, `OLLAMA_MODEL=llama3.2`.

Structured JSON replies use Ollama’s **`format: json`** mode so the research schema parses reliably.

### Optional: OpenAI (cloud)

If you prefer a hosted API: `uv sync --extra openai`, set `LLM_PROVIDER=openai`, `OPENAI_API_KEY`, and `LLM_MODEL`.

## Other features

- **News sentiment (FinBERT)**: Headlines from the research bundle are scored with [ProsusAI/finbert](https://huggingface.co/ProsusAI/finbert) when optional deps are installed (`uv sync --extra sentiment`). Without them, the API still works and reports `news_sentiment.enabled: false`.
- **Data**: Multi-provider market data (existing `DataService` / registry).
- **Research**: `POST /api/research/check` with `include_ai: true` runs the LLM (Ollama or OpenAI) for conviction (0–100), stance, thesis, bull/bear, risks, plus heuristic **evaluation** and **guardrail** warnings. Optional **investor personas** (`persona`) or **committee** mode (multiple personas + portfolio-manager synthesis). See `GET /api/research/personas`.
- **Simulation**: `POST /api/simulation/backtest` builds the same snapshot with **price history ending on `as_of_date`** (fundamentals/news may still be latest from providers — see response `simulation_note`). Optional AI with the same `persona` / `committee` fields as research.
- **Third-party ideas**: Persona/committee flow is inspired by [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) (MIT); see [third_party/ATTRIBUTION.md](third_party/ATTRIBUTION.md).
- **Portfolio**: Persistent book in `./data/fund.db` — buy/sell, cash, splits, dividends, manual edits. Can **seed** from `config/portfolio.json` when the DB has no positions.
- **Risk**: `GET /api/portfolio/risk` uses **value-weighted** daily returns.

## Quick start

```bash
cd ai-hedge-fund
cp .env.example .env
# Edit OLLAMA_MODEL to match `ollama list`

uv sync --extra dev
uv run uvicorn hedge_fund.api.main:app --reload   # :8000

cd frontend && npm install && npm run dev           # :5173
```

CLI: `uv run check-data AAPL`

## Environment reference

| Variable | Purpose |
|----------|---------|
| `LLM_PROVIDER` | `ollama` (default) or `openai` |
| `OLLAMA_BASE_URL` | Ollama HTTP API (default `http://127.0.0.1:11434`) |
| `OLLAMA_MODEL` | Model name from `ollama list` |
| `OLLAMA_TIMEOUT_S` | Long timeout for slow local GPUs (default 600) |
| `DATABASE_URL` | Override SQLite path |
| `OPENAI_API_KEY` | Only if `LLM_PROVIDER=openai` |
| `LLM_MAX_OUTPUT_TOKENS` | Cap generation length |
| `RESEARCH_MAX_CONTEXT_CHARS` | Truncate JSON context sent to the model |

## API overview

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/research/check` | Body: `{ ticker, include_ai?, persona?, committee?, committee_personas? }` |
| GET | `/api/research/personas` | Valid `persona` ids and default committee list |
| POST | `/api/simulation/backtest` | Body: `{ ticker, as_of_date, price_lookback_days?, include_ai?, persona?, committee?, committee_personas? }` |
| GET | `/api/portfolio` | Holdings + live marks |
| GET | `/api/portfolio/risk` | Weighted VaR / Sharpe / max DD |
| GET | `/api/portfolio/transactions` | Ledger |
| POST | `/api/portfolio/buy`, `/sell`, `/cash/*`, `/corporate/*` | Trades & corp actions |
| PATCH | `/api/portfolio/holdings/{ticker}` | Manual `shares` / `avg_cost` |

## Tests

```bash
uv run pytest tests/ -q
```

## CI (GitHub Actions)

The workflow lives at **`.github/workflows/ci.yml`** next to the `ai-hedge-fund/` folder (workspace root). It runs Ruff, pytest, and `frontend` `npm ci && npm run build`.

If your Git repository root **is** `ai-hedge-fund` (not the parent folder), move that workflow file to `ai-hedge-fund/.github/workflows/ci.yml` and change every `working-directory` / path from `ai-hedge-fund` to `.` (or drop the prefix).

## Railway deployment

### Fast path (local CLI)

From **`ai-hedge-fund/`** after a one-time `railway login`:

```bash
./scripts/railway-bootstrap.sh
```

Then set `FRONTEND_URL` to your public Railway HTTPS URL (see script output). For GitHub deploys, add a [project token](https://docs.railway.com/integrations/api#project-token) as the **`RAILWAY_TOKEN`** repository secret; pushes to `main` run `.github/workflows/deploy-railway.yml`.

### Manual steps

1. Install the [Railway CLI](https://docs.railway.com/guides/cli) and run `railway login`.
2. From this directory: `railway init` (new project) or `railway link` (existing project). If the repo root is the parent folder, set **Root Directory** to `ai-hedge-fund` in the Railway service settings.
3. **Build** uses `Dockerfile` + `railway.toml`. The image builds the Vite client and serves it from FastAPI when `STATIC_DIR` is set (handled in the Dockerfile).
4. Set variables (dashboard or `railway variables`):

| Variable | Notes |
|----------|--------|
| `FRONTEND_URL` | Public site URL (e.g. `https://your-service.up.railway.app`) — required for CORS |
| `PORT` | Set automatically by Railway |
| `SENTRY_DSN` | Optional — Python/FastAPI errors |
| `SENTRY_ENVIRONMENT` | e.g. `production` |
| `SENTRY_TRACES_SAMPLE_RATE` | e.g. `0.1` |
| `VITE_SENTRY_DSN` | Same DSN as Sentry project for browser errors; must be present at **build** time for the client bundle |
| `VITE_SENTRY_ENVIRONMENT` | e.g. `production` |

5. Deploy from GitHub or run `railway up` after linking.

Health check path: **`/api/health`** (configured in `railway.toml`).
