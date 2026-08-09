from pydantic import BaseModel
from typing import Optional


class Incident(BaseModel):
    incident_id: str
    repository: str

    failed_run_id: int
    failed_workflow: str
    failed_commit: str

    root_cause: str
    confidence: float

    remediation_summary: str
    policy_decision: str

    recovery_branch: Optional[str] = None
    recovery_pr: Optional[int] = None
    recovery_pr_url: Optional[str] = None

    validation_run_id: Optional[int] = None
    validation_result: Optional[str] = None

    status: str