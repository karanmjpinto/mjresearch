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
The cache (`SHARED_VALUE_CACHE`) lives for the process and is shared across
requests, bounded at 1,024 entries with the oldest evicted. It used to be a
fresh dict per request, so the keys were right and nothing ever hit. Nodes that
read other nodes' facts (`consumes`) are never cached.

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

Binding is constrained so a number is not read against the wrong name: the
search stays inside the alias's own sentence or line; a number written as a
multiple, a percentage, or a currency amount is only offered to a metric of that
kind; window lengths ("30-day") and digits inside a metric's own name are not
values; a comparator between name and number ("RSI below 40") is tested as a
bound; and a figure attributed to peers or an average is `unverifiable`.

Binding runs in two passes. Every name first takes the number written after
it, and only names still without one may read backwards, among numbers nobody
took. In one pass a long alias could read backwards before the owner of the
number read forwards — "PEG ratio (2.67) suggests the stock is trading at a
premium" gave a share price of 2.67. A figure repeated later still owns its
number, and a field name the narrator quotes literally (`pe_ratio=38.69`) is an
alias of its metric.

Anything it cannot map is reported as `unverifiable`, never as passing — silence
about a claim must not look like a passing check.

In the plan pipeline the verifier also checks the plan's own outputs.
`specs_for_facts` builds one spec per numeric field the plan computed — the
fields are typed and named, `recent_volatility_pct`, which is what a checker
needs — so "recent volatility of 26.73%" is checked against the value the
executor produced. Before this the hand-written specs knew only snapshot
metrics, and on the first full eval most theses that quoted computed values
correctly were reported as citing nothing. One-word fields (`high`, `low`) are
skipped because they are ordinary words, a percentage field read by its name in
words must be written as a percentage, and a field the plan computed twice
(`annualized_return_pct` over two windows) accepts either true value.

### Repair: the checker sends work back once

The model proposes; code decides what is wrong and says so. Two stages get one
retry each (`MAX_REPAIRS = 1`), and the correction is written by code, not by a
second model:

- **Planner.** A plan the validator rejects goes back with the validator's own
  list of problems ("unknown metric", a parameter out of range). A second
  rejection is an error, not a loop. Recorded as `evaluation.plan_repair`.
  Two mistakes the harness fixes itself, without a model call, and records as
  `evaluation.plan_fixes`: a dependency written as a metric name is pointed at
  the one step running that metric, and a dependency on a metric no step runs
  adds that step — only when it is a registered metric that needs no
  parameters, so nothing the model did not choose is guessed.
- **Narrator.** The prose goes back when the thesis is empty, when a number
  contradicts a computed value (the retry quotes the excerpt, the number written
  and the correct one), or when it cites no computed value at all. The retry is
  verified again and the better-checked version is kept — fewer wrong numbers
  first, then citing something — so a repair can never make a run worse. Both
  verdicts are recorded as `evaluation.repair`, and the plan view says
  "corrected once by the checker" when the second draft won.

The empty-thesis trigger exists because of a live failure on the AAPL fixture:
under constrained decoding at temperature 0 the narrator returned every string
empty, which is valid JSON, cites nothing for the verifier to catch, and reads
as a cautious HOLD. The narrator prompt now says what each field must contain;
the trigger is the net under it.

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

It is also measured, the way Bridgewater measures PAT (95% output determinism on
their suite). `scripts/run_plan_eval.py` runs the thirty questions in
`evals/plan_questions.py` five times each against frozen snapshots and frozen
price histories (`evals/fixtures/prices/`), and reports plan agreement,
conclusion agreement (stance, conviction and verification status), the grounded
rate before and after repair, and coverage: the share of the questions whose
every needed capability has a registered metric. Results land in
`evals/results/plan-*.json`.

The script asks the questions round robin, never one twice in a row. The first
baseline asked each five times consecutively, and in 14 of the 15 questions
whose plans disagreed, only the first run differed: the model server reuses
the previous prompt's cache, and a warm repeat is computed differently from a
cold call. A user asks once, so the cold path is what is measured.

Measured on 17 October 2026, qwen3:30b, 30 questions × 5 runs
(`evals/results/plan-20261017T180758Z.json`):

| | first baseline | after Phase 1 |
|---|---|---|
| same plan from the same question | 88.5% | 95.9% |
| same conclusion from the same inputs | 91.5% | 96.6% |
| prose checks clean against computed values | 57.5% | 86.9% |
| clean on the first draft, before any repair | 56.7% | 80.0% |
| errored runs | 16 of 150 | 5 of 150 |
| questions the catalog can answer | 14 of 30 | 14 of 30 |

Every remaining disagreement was the first pass of a question against its later
passes; passes two to five agreed completely. The cause is the model server
matching a prompt it cached on an earlier pass. With `--unload-between-passes`,
which stops the model before each pass so every call is cold, both agreements
are **100%** across all 145 completed runs (`plan-20261017T190020Z.json`;
grounded 86.2%, first draft 79.3%, the same five errored runs). The pipeline is
reproducible; the residue was the server's cache.

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
- The metric catalog answers 14 of the 30 eval questions. The rest are blocked
  by capabilities no metric provides yet — revenue growth history, margin
  trend, cash conversion, macro sensitivity, capital return, peer comparison,
  balance-sheet strength, event studies and operating leverage. The tally is
  `coverage()` in `evals/plan_questions.py`.
- The committee path has no repair loop; only the plan pipeline does.
- `research_run_retention` trimming exists (`prune_runs`) but is not scheduled.
- The frontend covers the plan pipeline and the older committee path, but there
  is no UI for run history, run comparison, or methodology notes — those are API
  and MCP only.
