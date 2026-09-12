"""Your own notes, treated as a source with provenance like any other."""

from hedge_fund.knowledge.match import Match, coverage, match_ticker
from hedge_fund.knowledge.vault import Note, VaultIndex, build_index, vault_root

__all__ = ["Match", "Note", "VaultIndex", "build_index", "coverage", "match_ticker", "vault_root"]
