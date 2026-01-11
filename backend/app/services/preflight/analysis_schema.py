"""
Analysis Result Schema
Pydantic models for LLM (DeepSeek R1) analysis output
"""

from pydantic import BaseModel, Field
from typing import List, Literal


class AnalysisResult(BaseModel):
    """LLM analysis result for upgrade readiness"""

    verdict: Literal["GO", "NO-GO", "CAUTION"] = Field(
        description="Overall upgrade readiness verdict"
    )

    reasoning_summary: str = Field(
        description="Concise summary of the analysis reasoning"
    )

    blockers: List[str] = Field(
        default_factory=list,
        description="Critical issues that block the upgrade"
    )

    risks: List[str] = Field(
        default_factory=list,
        description="Warning-level issues that need attention"
    )

    action_plan: List[str] = Field(
        default_factory=list,
        description="Ordered steps to resolve issues before upgrade"
    )
