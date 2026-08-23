# Contributing

Thanks for taking an interest. This is a personal research tool that is open to
contributions — issues and pull requests are both welcome.

## Ground rules

The project has one organising principle: **the language model never produces a number.**
Any change that lets a model's output become a figure a user might act on — a metric, a
score, a weight — will be sent back, however convenient it is. If you need a new number,
add a deterministic metric to the catalog and let the planner select it.

The second principle is that **limitations are documented as prominently as features.**
If your change narrows what the tool can verify, say so in the same PR.

## Development setup

Prerequisites: [uv](https://docs.astral.sh/uv/), Node 20+, and [Ollama](https://ollama.com).

```bash
git clone https://github.com/karanmjpinto/mjresearch.git
cd mjresearch/ai-hedge-fund

cp .env.example .env          # set OLLAMA_MODEL to a name from `ollama list`
uv sync --extra dev

cd frontend && npm install && cd ..

./start.sh                    # API on :8000, UI on :5173
```

## Before you open a PR

Run what CI runs:

```bash
cd ai-hedge-fund

uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest -q

cd frontend && npm run build
```

All four must pass. CI additionally runs a design review over changed UI files and
fails on critical findings.

## What makes a change easy to merge

- **One concern per PR.** A bug fix and a refactor in the same diff take three times as
  long to review.
- **A test that fails before and passes after.** For anything touching the plan pipeline,
  the verifier, provenance, or portfolio arithmetic, this is not optional — those are the
  parts where a silent regression is indistinguishable from a correct answer.
- **Say why, not what.** The diff already shows what changed. Commit messages and
  comments should carry the reasoning that is not recoverable from the code.
- **Conventional Commits.** `feat(scope):`, `fix(scope):`, `docs:`, `refactor(scope):`,
  `chore:`. Keep the subject in the imperative and under ~72 characters.

## Code style

- **Python** — Ruff for both lint and format, targeting 3.12. Type hints on anything
  crossing a module boundary.
- **TypeScript/React** — the design system lives in
  [`ai-hedge-fund/DESIGN.md`](ai-hedge-fund/DESIGN.md). Colours and sizes belong in
  `tailwind.config.ts` or `src/index.css` as named tokens, not inline at call sites. No
  hex literals and no stock Tailwind greys in components. 12px is the type floor, named
  as `fontSize.label`.

## Reporting bugs

Open an issue with the template. The two things that make a report actionable are the
**exact command or request** and the **full response or traceback**. For anything
involving research output, include the run id — `GET /api/runs/{uid}` returns the exact
data the model saw, which is usually where the answer is.

Security vulnerabilities go through [SECURITY.md](SECURITY.md), not the public tracker.

## A note on scope

Some things are deliberately absent and are unlikely to be accepted:

- **Authentication for the API.** The design assumes it is bound to localhost. Adding
  half of an auth system invites people to expose it.
- **A hosted instance with a shared portfolio.** The book is single-tenant by design.
- **Live trading or broker integration.** This is a research tool; it does not place
  orders, and it should stay that way.

## License

By contributing you agree that your contributions are licensed under the
[MIT License](LICENSE).
