from datetime import datetime

from src.models.incident import Incident


def create_incident(
    repository: str,
    run,
    rca_result,
    remediation_result,
    policy_result,
) -> Incident:

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    return Incident(
        incident_id=f"INC-{timestamp}",
        repository=repository,

        failed_run_id=run["id"],
        failed_workflow=run["name"],
        failed_commit=run["head_sha"],

        root_cause=rca_result.root_cause,
        confidence=rca_result.confidence,

        remediation_summary=remediation_result.summary,
        policy_decision=policy_result.decision,

        status="REMEDIATION_PROPOSED",
    )