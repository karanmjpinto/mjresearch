# Agent memory (continual learning)

## Learned User Preferences

- Default to local, free, open-source LLM inference via **Ollama** for research; treat cloud OpenAI as optional when `LLM_PROVIDER=openai` and keys are set.
- When the user asks to run or deploy locally, **execute** commands (start API/UI, verify health) rather than only listing steps.
- Keep third-party API keys in **`.env`** (gitignored); do not paste secrets into chat—if a key is exposed, advise rotation.

## Learned Workspace Facts

- The shipped app lives under **`ai-hedge-fund/`**: FastAPI (default **:8000**) and Vite (default **:5173**); the dev server proxies **`/api`** to the backend.
- Market data uses **`DataService`** → **`ProviderRegistry`**; **OpenBB** is the primary provider for core equity paths (price, fundamentals, technicals, news) with fallbacks such as yfinance.
- **`load_dotenv`** runs when the data service module loads so **`os.getenv`** in providers (e.g. Alpha Vantage) reads **`.env`**, not only Pydantic settings.
- Upstream-style named investors (e.g. Buffett) are implemented as **`persona_id`** strings and committee flows in **`agents/personas.py`** and the research/simulation APIs—not separate agent modules per name.
- **Tickers** are not a fixed whitelist: symbols must pass **`sanitize_ticker`** / guardrail format rules; real coverage depends on configured providers. Example groups live in **`config/watchlists.json`**.
- Optional **FinBERT** headline sentiment uses the **`[sentiment]`** extra (`uv sync --extra sentiment`); see **`NEWS_SENTIMENT_ENABLED`** / **`FINBERT_MODEL_ID`** and the README when that path matters.
- **`OLLAMA_MODEL`** in **`.env`** should match an installed Ollama model (e.g. **`llama3.2`** aligns with **`llama3.2:latest`** from **`ollama list`**).
- The frontend includes a **Screeners** top-nav area for multiple screening views (plays with entry/sizing, etc., as wired).
