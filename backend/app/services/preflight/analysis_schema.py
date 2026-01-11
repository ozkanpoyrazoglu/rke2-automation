"""
Analysis Result Schema
Pydantic models for LLM (DeepSeek R1) analysis output
"""

from pydantic import BaseModel, Field
from typing import List, Literal, Optional


class FindingsPerLayer(BaseModel):
    """Categorized findings by infrastructure layer"""
    os_layer: List[str] = Field(default_factory=list, description="OS-level findings")
    etcd_health: List[str] = Field(default_factory=list, description="Etcd health findings")
    kubernetes_layer: List[str] = Field(default_factory=list, description="Kubernetes findings")
    network_layer: List[str] = Field(default_factory=list, description="Network findings")
    workload_safety: List[str] = Field(default_factory=list, description="Workload safety findings")


class AnalysisResult(BaseModel):
    """LLM analysis result for upgrade readiness"""

    verdict: Literal["GO", "NO-GO", "CAUTION"] = Field(
        description="Overall upgrade readiness verdict"
    )

    reasoning_summary: str = Field(
        description="Concise summary of the analysis reasoning"
    )

    findings: Optional[FindingsPerLayer] = Field(
        default=None,
        description="Categorized findings by infrastructure layer (Bulgular)"
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
