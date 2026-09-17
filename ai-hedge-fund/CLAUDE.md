# AI Hedge Fund — agent notes

## Document the change with the change

`frontend/src/content/docs.ts` is the reference section, served at `/docs`
outside the backend gate. When you add or change a feature, update it **in the
same change** — not afterwards, not in a follow-up.

Two things make this non-optional rather than a good intention:

- Every capability listed there carries a `trust` label (`computed`,
  `chosen-then-computed`, `written`, `judged`). A reader deciding whether to
  act on a number needs to know whether it was calculated or predicted, and
  nothing else in the app tells them. A new capability without a label is the
  one kind of omission that actively misleads.
- `tests/test_docs_coverage.py` fails if a screen in `cache.SCREENS` or a
  member of `DEFAULT_COMMITTEE_PERSONAS` is never mentioned in the docs. It
  cannot check that the prose is good; it can refuse to let a feature exist
  that the docs have never heard of.

The `gaps` list is part of the deliverable, not a disclaimer. A reference that
describes only what works teaches the reader to trust the parts that don't.

## Design System

Always read `DESIGN.md` before making any visual or UI decisions.  
All font choices, colors, spacing, and aesthetic direction are defined there.  
Do not deviate without explicit user approval.  
In QA mode, flag any code that does not match `DESIGN.md`.
