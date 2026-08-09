from pydantic import BaseModel
from typing import List


class RemediationResult(BaseModel):
    summary: str
    target_file: str
    proposed_change: str
    patch: str
    reasoning: str
    validation_steps: List[str]
    risk: str
    requires_human_approval: bool