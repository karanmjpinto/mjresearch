"""Structured LLM outputs (validated with Pydantic)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ConvictionFactor(BaseModel):
    factor: str = Field(max_length=300, description="One material point from the data")
    points: int = Field(ge=-25, le=25, description="How far it moves the case for owning")


class ResearchAnalysisOutput(BaseModel):
    # First, so the model weighs the points before it writes the number. Asked
    # for a bare score it picked 50 or 75 in 40% of runs; the score is now
    # computed from these in `research_agent._finalize`.
    conviction_factors: list[ConvictionFactor] = Field(
        default_factory=list, max_length=8, description="Signed points the score is built from"
    )
    conviction_score: int = Field(ge=0, le=100, description="0–100 investment conviction")
    # A Literal rather than a free string: it becomes an enum in the JSON
    # schema, so grammar-constrained decoding cannot emit anything else.
    stance: Literal["BUY", "HOLD", "SELL", "WATCH"]
    investment_thesis: str = Field(max_length=12_000)
    bull_case: str = Field(max_length=4000)
    bear_case: str = Field(max_length=4000)
    key_risks: list[str] = Field(default_factory=list, description="Up to 12 material risks")
    time_horizon: str = Field(
        default="medium_term", description="e.g. short_term, medium_term, long_term"
    )
    confidence_in_data: int = Field(ge=1, le=5, description="How complete the data felt")
