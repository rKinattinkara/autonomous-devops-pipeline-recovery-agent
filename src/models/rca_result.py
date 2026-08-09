from pydantic import BaseModel
from typing import List


class RCAResult(BaseModel):
    failure_category: str
    failed_component: str
    root_cause: str
    evidence: List[str]
    recommended_action: str
    confidence: float
    risk: str