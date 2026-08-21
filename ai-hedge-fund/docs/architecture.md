# Research architecture

Two pipelines share one data layer. The older one asks a model for a verdict; the
newer one compiles the question into a program and lets the model narrate the
result. Both now run inside a harness that records what happened and checks the
output against the data.

## Why the second pipeline exists

Handing a model a JSON dump and asking for a conviction score makes every number
in the answer a token prediction. The figures read exactly like correct ones, so
the errors that matter are the ones that survive review. The fix is structural
rather than prompt-level: move the arithmetic out of the model.

```
question ──▶ planner (LLM)  ──▶ typed plan (DAG of metric nodes)
                                     │
snapshot ───────────────────────────▶ executor (plain Python)
                                     │
                              computed facts
                                     │
                              narrator (LLM, no arithmetic)
                                     │
                              harness checks ──▶ recorded run
```

The model appears twice, in two narrow roles. The planner chooses *what to
measure* and never sees a value. The narrator sees only values the executor
produced. Neither is in a position to invent a figure and then reason from it.

## The layers

### Snapshot (`api/research_snapshot.py`)

The unit of analysis. Fetched once, then frozen: every persona in a committee
reads the same object, so a disagreement between them is a difference of
judgement rather than of data. It carries its own provenance.

### Provenance (`data/provenance.py`)

A fallback chain can change data sources between two otherwise identical runs.
Providers disagree on split adjustment, fiscal-period alignment, and currency, so
every fetch records which provider answered, whether it came from cache, and how
the payload verified — frequency, date range, point count, units, adjustment
basis. Collected via `contextvars`, so no call site had to change.

Verification results are advisory, and surface as `data_quality.warnings`.

### Metric registry (`plan/registry.py`)

Every number an analysis can rest on. Each metric declares its parameters and
every field it emits, each with a semantic description — the natural-language
half of a type signature. `GET /api/research/metrics` serves the catalog; it is
also exactly what the planner is shown.

Adding a metric is the way to extend what the system can conclude:

```python
register(Metric(
    id="my_metric",
    label="…", description="…", tier="transform",
    params=(ParamSpec("days", "integer", "…", default=90, minimum=5, maximum=3650),),
    outputs=(FieldSpec("value", "number", "what this means", "%"),),
    fn=lambda ctx, days: {"value": ...},
))
```

Outputs are validated against the signature, so a metric that returns a field it
did not declare fails loudly rather than reaching the prompt.

### Plan (`plan/schema.py`, `plan/executor.py`)

A DAG of nodes, validated statically before anything runs: metric ids exist,
parameters typecheck and are in range, dependencies resolve, no cycles. Every
ambiguity resolved here is one that cannot resurface as a wrong number later.

Node values are content-addressed by `(snapshot, metric, params)`, so editing one
node does not re-run the others — which is what makes iterating on a plan cheap.

A failing node degrades the plan rather than aborting it: the node carries its
error, dependants are skipped, and independent work still computes. A partial
result with an explicit gap beats a gap that has been quietly filled in.

### Clarifications

Plans may carry methodology questions — closed-form, 2–4 options, with a
recommendation. They are answered *before* execution, so the choice is compiled
into the plan instead of being resolved silently mid-run. Unanswered questions
fall back to the recommendation, and the fact that it was not confirmed is stated
in the prompt and in `clarifications_pending`.

### The harness has the last word

When a plan computes a conviction score, it replaces whatever the narrator wrote
and the substitution is recorded in `harness_overrides`. The score is then
reproducible from the plan alone.

### Claim verification (`agents/verifier.py`)

A deterministic pass, not a second model. It anchors on metric names, reads the
nearest number, and compares against the snapshot within a per-metric tolerance.
Longer aliases resolve first so a specific metric claims its number before a
generic one; each number is consumed once; direction words set the sign.

Anything it cannot map is reported as `unverifiable`, never as passing — silence
about a claim must not look like a passing check.

### Recorded runs (`runs/`)

Every analysis persists its snapshot (deduplicated by content hash), prompts,
model parameters, output, and checks.

- `snapshot_sha256` — the data, ignoring fetch timestamps
- `run_key` — the whole determined input set: data, prompt, model, parameters
- `plan_hash` — a plan's executable content, ignoring prose

Two runs sharing a `run_key` should agree. `GET /api/runs/compare` sets
`nondeterminism_detected` when they do not, which means results are not yet
reproducible and any eval built on them would be measuring noise.

Persistence is best-effort: a storage failure degrades observability, never the
analysis.

### Methodology memory (`agents/memory.py`)

Corrections of *method*, carried between runs — "break case studies out by asset
class rather than reporting an aggregate". Two deliberate constraints:

- **Only method text is stored.** Notes containing prices, amounts, or scores are
  rejected. A stored number would be replayed onto every future run, where it
  will not be true.
- **Notes are retrieved, not accumulated.** Only notes matching the ticker and
  persona scope enter the prompt, and the ids used are recorded on the run, so a
  conclusion can be traced back to the guidance that shaped it.

## Determinism

Sampling is greedy and seeded (`llm_temperature=0.0`, `llm_seed=7`), and the
parameters are recorded on every run. Providers do not guarantee bit-for-bit
determinism — batching, quantisation and hardware all leak in — so the goal here
is narrower and achievable: pin and record the inputs, so any remaining variance
is attributable rather than ambient. The structural fix is the plan pipeline,
where the numbers do not come from the model at all.

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/research/metrics` | Metric catalog with typed signatures |
| POST | `/api/research/plan` | Plan → execute → narrate |
| GET | `/api/research/graph/plan` | Plan pipeline structure |
| GET | `/api/runs` | Recorded runs |
| GET | `/api/runs/{uid}` | One run, with its snapshot |
| GET | `/api/runs/compare?a=&b=` | Diff two runs; detect nondeterminism |
| GET | `/api/runs/snapshot/{hash}` | Stored snapshot, for replay |
| GET | `/api/methodology` | Stored lessons |
| GET | `/api/methodology/applicable` | Notes that would enter a prompt now |
| POST | `/api/methodology` | Teach a lesson |
| DELETE | `/api/methodology/{id}` | Retire a lesson |

Replay a past run exactly:

```bash
curl -s localhost:8000/api/runs/<uid> | jq -r .snapshot_sha256
curl -s -X POST localhost:8000/api/research/plan \
  -H 'content-type: application/json' \
  -d '{"ticker":"AAPL","replay_snapshot":"<hash>"}'
```

## Deployment posture

The backend is not deployed. It has no authentication and exposes write
endpoints (`buy`, `sell`, `cash/withdraw`, holdings edits) against a real book,
so a public instance would be an unauthenticated financial API. GitHub Pages
serves the landing page; `BackendGate` explains the missing API on app routes
rather than letting each panel fail on its own.

If that changes, auth comes first, not after.

## Known limits

- Verification tolerances are absolute, not sector-relative. `valuation_score`
  bands are the same for a utility and a software company.
- The claim verifier covers the metrics in `METRIC_SPECS`. Prose claims outside
  that set are counted as unverifiable, not checked.
- Committee mode still runs full-freedom personas. Turning personas into weight
  profiles over the plan's dimension scores would make committee conviction as
  auditable as the plan's, and is not done.
- `research_run_retention` trimming exists (`prune_runs`) but is not scheduled.
- The frontend covers the plan pipeline and the older committee path, but there
  is no UI for run history, run comparison, or methodology notes — those are API
  and MCP only.
