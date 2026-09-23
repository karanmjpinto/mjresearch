"""Factor data from Jensen, Kelly and Pedersen (jkpfactors.com), and where one
company sits on it.

Two halves, kept apart because they are different kinds of claim:

- `jkp` serves the authors' published long-short factor returns and computes
  plain statistics over them. Nothing is re-estimated; the returns are theirs.
- `exposure` ranks one company against a cross-section of names on the subset
  of JKP characteristics this app's data can measure, and says which it cannot.
"""
