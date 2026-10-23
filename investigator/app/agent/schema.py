from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    tool: str = Field(description="Name of the tool or evidence source (e.g. 'query_prometheus', 'search_logs', 'container_status', 'metrics', 'timeline')")
    input: str = Field(description="Input query or parameter used")
    finding: str = Field(description="Concrete finding or observation")


class RootCause(BaseModel):
    rank: int = Field(description="Ranking of the root cause hypothesis (1 is most likely)")
    service: str = Field(description="The service identified as the root cause")
    summary: str = Field(description="Detailed explanation of the failure mechanism and root cause")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")
    evidence: List[EvidenceItem] = Field(min_length=1, description="List of supporting evidence items")


class InvestigationReport(BaseModel):
    target_service: str = Field(description="Service that was requested for investigation")
    status: str = Field(default="completed", description="Investigation status")
    summary: str = Field(description="Executive summary of the incident")
    root_causes: List[RootCause] = Field(min_length=1, description="Ranked list of verified root causes")


class AgentStepEvent(BaseModel):
    step: int
    type: str  # "thought", "tool_call", "tool_result", "final_answer", "error"
    content: str
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    tool_result: Optional[Any] = None
    timestamp: float
