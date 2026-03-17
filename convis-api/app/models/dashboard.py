from pydantic import BaseModel, Field
from typing import Dict, List, Optional


class AssistantSentimentBreakdown(BaseModel):
    positive: int = 0
    negative: int = 0
    neutral: int = 0
    unknown: int = 0


class AssistantStatusBreakdown(BaseModel):
    statuses: Dict[str, int] = Field(default_factory=dict)


class AssistantSummaryItem(BaseModel):
    assistant_id: Optional[str]
    assistant_name: str
    total_calls: int = 0
    total_duration_seconds: float = 0.0
    total_cost: float = 0.0
    sentiment: AssistantSentimentBreakdown = Field(default_factory=AssistantSentimentBreakdown)
    status_counts: Dict[str, int] = Field(default_factory=dict)


class AssistantSummaryResponse(BaseModel):
    timeframe: str
    total_cost: float
    total_calls: int
    assistants: List[AssistantSummaryItem]
