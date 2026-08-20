# AI Hedge Fund

Local **AI research** (default: **Ollama**) plus a **SQLite portfolio** with trades, corporate actions, and **value-weighted risk**. Stack: FastAPI, SQLAlchemy, React/Vite.

## LLM: free and open-source (recommended)

**[Ollama](https://ollama.com)** is the default: it runs open-weight models (Llama, Mistral, Qwen, etc.) on your machine — **no API keys**, **no usage fees**.

1. Install Ollama from the site above (macOS/Linux/Windows).
2. Pull a model (pick one you have or try a small one first):

   ```bash
   ollama pull qwen3:30b
   # or: ollama pull mistral / qwen2.5 / etc.
   ollama list
   ```

3. Ensure the daemon is up (usually automatic). If needed: `ollama serve`.
4. Point the app at your model in `.env`:

   ```bash
   cp .env.example .env
   # Set OLLAMA_MODEL to a name from `ollama list` (e.g. qwen3:30b, qwen2.5:32b, …)
   ```

5. Defaults: `LLM_PROVIDER=ollama`, `OLLAMA_BASE_URL=http://127.0.0.1:11434`, `OLLAMA_MODEL=qwen3:30b`.

   **Model choice matters for research quality.** `qwen3:30b` is a mixture-of-experts
   model — ~30B total parameters but only ~3B active per token, so it reasons far
   better than a small dense model at comparable speed. Smaller models tend to write
   theses that cite none of the computed values; the harness flags that as
   `narrative_grounded: false`, but a capable model avoids it in the first place.

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
- **Backtesting**: `GET /api/backtest/{ticker}?strategy=X` — six vectorized strategies (buy & hold, golden cross, RSI reversion, Bollinger breakout, trend-plus-drawdown, 6-month momentum). No look-ahead bias, 5 bps fee per side, full metrics (Sharpe, Sortino, Calmar, max DD, win rate, round-trip log).
- **Portfolio construction**: `POST /api/optimize` — five allocation methods: equal weight, AI conviction weighted, inverse volatility, Markowitz max-Sharpe, and **Hierarchical Risk Parity** (Lopez de Prado 2016). Takes a basket + optional `convictions` map; returns weights, per-asset stats, and simulated daily-rebalance performance vs 1/N.
- **Alt data (EDGAR)**: SIC-classified peer groups and real SEC filings (10-K / 10-Q / 8-K / Form 4 / 13F-HR / DEF 14A / SC 13G-D) — no API key, just a descriptive `SEC_USER_AGENT`.
- **Parallel committee**: Committee mode runs personas concurrently via `asyncio.gather` (3-4× speedup vs sequential). `GET /api/research/graph` returns a JSON description of the fan-out/reduce workflow for visualization.

## Plan-based research (deterministic numbers)

`POST /api/research/plan` compiles a question into a **typed plan** — a DAG of
deterministic metrics — executes it in plain Python, and only then asks a model to
write the thesis over the computed values.

The model never produces a number. It appears twice, in two narrow roles: a
**planner** that picks metrics from a fixed catalog and sees no values, and a
**narrator** that sees only computed values under an explicit no-arithmetic rule.
When the plan computes a conviction score it replaces whatever the narrator
wrote, and the substitution is reported in `harness_overrides`.

```bash
curl -s -X POST localhost:8000/api/research/plan \
  -H 'content-type: application/json' \
  -d '{"ticker":"AAPL","question":"Is this attractive at current levels?","style":"deep value"}'
```

- `GET /api/research/metrics` — the metric catalog, with typed signatures and a
  semantic description for every field a metric emits.
- Plans may raise **methodology clarifications**: closed-form questions with a
  recommended default, answered *before* execution so the choice is compiled into
  the plan rather than resolved silently mid-run. Answer them by passing
  `clarification_answers: {"<id>": "<option>"}`.
- Pass `plan_override` to re-run an edited plan without re-planning. Node values
  are content-addressed, so unchanged nodes are not recomputed.

See [docs/architecture.md](docs/architecture.md) for the full design.

## Reproducible runs

Every analysis is recorded: the immutable snapshot (deduplicated by content
hash), the prompts, the model and its sampling parameters, the output, and the
checks that ran over it.

| Endpoint | Purpose |
|----------|---------|
| `GET /api/runs` | Recent runs |
| `GET /api/runs/{uid}` | One run, with the exact data it saw |
| `GET /api/runs/compare?a=&b=` | Diff two runs |
| `GET /api/runs/snapshot/{hash}` | Stored snapshot, for replay |

`compare` sets **`nondeterminism_detected`** when two runs with identical inputs
reached different conclusions — that is the signal that results are not yet
reproducible, and that any eval built on them would be measuring noise.

Sampling defaults to greedy and seeded (`LLM_TEMPERATURE=0.0`, `LLM_SEED=7`).
Replay a past run against its stored snapshot with
`{"ticker":"AAPL","replay_snapshot":"<hash>"}`.

## Data provenance

Provider fallback used to be invisible: two identical runs could resolve to
different sources, which disagree on split adjustment, fiscal-period alignment
and currency. Every fetch now records which provider answered, whether it came
from cache, and how the payload verified — frequency, date range, point count,
units, adjustment basis. Results surface as `data_quality` on research responses
and `provenance` inside the snapshot.

## Teaching methodology

When an analysis comes out wrong, the durable lesson is usually the *method*, not
the number. `POST /api/methodology` stores a portable correction that later runs
apply:

```bash
curl -s -X POST localhost:8000/api/methodology \
  -H 'content-type: application/json' \
  -d '{"note":"Break case-study comparisons out by asset class rather than reporting only an aggregate."}'
```

Notes containing prices, amounts, or scores are **rejected** — a stored number
would be replayed onto every future run, where it will not be true. Scope a note
to a ticker or persona, or leave it global. `GET /api/methodology/applicable`
shows exactly what would enter a prompt right now, and each run records which
notes shaped it.

## MCP server (Claude Desktop, Cursor, etc.)

The full stack is exposed as an **MCP server** so you can drive it from any MCP-compatible client. Thirteen tools: `research_ticker`, `plan_research`, `list_metrics`, `get_market_data`, `get_sec_filings`, `get_peers`, `run_backtest_tool`, `optimize_portfolio`, `describe_research_graph`, `list_runs`, `get_run`, `compare_runs`, `teach_methodology`.

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "ai-hedge-fund": {
      "command": "uv",
      "args": ["run", "hedge-fund-mcp"],
      "cwd": "/absolute/path/to/ai-hedge-fund"
    }
  }
}
```

Restart Claude Desktop. You can now ask "use the ai-hedge-fund server to research NVDA with the committee" or "run a golden cross backtest on AAPL for 3 years" and the client will invoke the tools directly.

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
| `RESEARCH_MAX_CONTEXT_CHARS` | Reduce the JSON context sent to the model (field-aware, always valid JSON) |
| `LLM_TEMPERATURE` | Sampling temperature (default `0.0` — greedy, for reproducibility) |
| `LLM_SEED` | Sampling seed (default `7`) |
| `LLM_TOP_P` | Nucleus sampling cutoff (default `1.0`) |
| `RESEARCH_RUN_PERSISTENCE` | Record every run for replay and diffing (default `true`) |
| `RESEARCH_RUN_RETENTION` | Runs to keep when pruning (default `2000`) |

## API overview

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/research/check` | Body: `{ ticker, include_ai?, persona?, committee?, committee_personas? }` |
| POST | `/api/research/plan` | Typed-plan analysis: `{ ticker, question?, style?, clarification_answers?, plan_override?, replay_snapshot? }` |
| GET | `/api/research/metrics` | Deterministic metric catalog with typed signatures |
| GET | `/api/research/graph/plan` | Plan pipeline structure |
| GET | `/api/runs`, `/api/runs/{uid}`, `/api/runs/compare` | Recorded runs, replay, and drift detection |
| GET/POST/DELETE | `/api/methodology` | Learned methodology notes |
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
