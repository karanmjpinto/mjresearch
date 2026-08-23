## What this changes

<!-- The reasoning that is not recoverable from the diff. What was wrong, and why this
     is the right fix rather than a nearby one. -->

## How it was verified

<!-- The test that fails before and passes after, or the steps you ran. Required for
     anything touching the plan pipeline, the verifier, provenance, or portfolio
     arithmetic. -->

## Checklist

- [ ] `uv run ruff check src tests` and `uv run ruff format --check src tests` pass
- [ ] `uv run pytest -q` passes
- [ ] `npm run build` passes (if the frontend changed)
- [ ] No new figure originates from the language model
- [ ] Docs updated if this changes behaviour, or narrows what can be verified
