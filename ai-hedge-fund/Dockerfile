# Frontend (Vite) — Sentry DSN is baked at build time if passed as build-arg
FROM node:20-alpine AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ARG VITE_SENTRY_DSN
ARG VITE_SENTRY_ENVIRONMENT=production
ARG VITE_SENTRY_TRACES_SAMPLE_RATE=0.1
ENV VITE_SENTRY_DSN=$VITE_SENTRY_DSN
ENV VITE_SENTRY_ENVIRONMENT=$VITE_SENTRY_ENVIRONMENT
ENV VITE_SENTRY_TRACES_SAMPLE_RATE=$VITE_SENTRY_TRACES_SAMPLE_RATE
RUN npm run build

# API + static SPA
FROM python:3.12-slim
WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY config ./config
# The JKP factor returns are a committed, dated file rather than a live fetch,
# so the Factors tab answers on the hosted site too. The screen caches are not
# copied: they are built by a local refresh, and the tab says so when absent.
COPY data/factors ./data/factors
# The openai extra ships the client for every OpenAI-compatible endpoint, not
# just OpenAI's own — a hosted deployment has no local Ollama to fall back to,
# so leaving it out makes LLM_PROVIDER=openai a runtime ImportError that only
# surfaces on the first research call, long after the healthcheck went green.
RUN mkdir -p data && uv sync --frozen --no-dev --extra openai

COPY --from=frontend-build /build/dist ./frontend/dist

ENV STATIC_DIR=/app/frontend/dist
ENV PORT=8000
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD sh -c 'exec /app/.venv/bin/uvicorn hedge_fund.api.main:app --host 0.0.0.0 --port "${PORT:-8000}"'
