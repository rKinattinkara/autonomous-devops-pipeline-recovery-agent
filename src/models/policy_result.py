from pydantic import BaseModel
from typing import List


class PolicyResult(BaseModel):
    decision: str
    risk: str
    reasons: List[str]
    allowed_to_execute: bool
    requires_human_approval: bool