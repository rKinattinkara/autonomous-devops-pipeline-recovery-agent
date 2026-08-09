from src.models.remediation_result import RemediationResult
from src.models.policy_result import PolicyResult

from src.recovery.patch_engine import apply_simple_patch

from src.tools.github_recovery import (
    create_recovery_branch,
    get_file,
    decode_file_content,
    update_file,
    create_pull_request,
)


def execute_recovery(
    remediation: RemediationResult,
    policy: PolicyResult,
    failed_commit_sha: str,
    run_id: int,
):

    # ---------------------------------------------------------
    # Safety gate
    # ---------------------------------------------------------

    if not policy.allowed_to_execute:
        raise PermissionError(
            f"Recovery blocked by policy: "
            f"{policy.decision}"
        )

    if policy.decision != "ALLOW":
        raise PermissionError(
            "Only ALLOW decisions may execute automatically."
        )

    print(
        "Safety policy approved automated recovery."
    )

    # ---------------------------------------------------------
    # Create recovery branch
    # ---------------------------------------------------------

    branch_name = create_recovery_branch(
        failed_commit_sha,
        run_id,
    )

    print(
        f"Created recovery branch: {branch_name}"
    )

    # ---------------------------------------------------------
    # Retrieve target file
    # ---------------------------------------------------------

    file_data = get_file(
        remediation.target_file,
        branch_name,
    )

    current_content = decode_file_content(
        file_data
    )

    # ---------------------------------------------------------
    # Apply controlled patch
    # ---------------------------------------------------------

    updated_content = apply_simple_patch(
        current_content,
        remediation.patch,
    )

    print("Patch validated.")

    # ---------------------------------------------------------
    # Commit updated file
    # ---------------------------------------------------------

    update_file(
        file_path=remediation.target_file,
        branch=branch_name,
        new_content=updated_content,
        current_file_sha=file_data["sha"],
        commit_message=(
            "fix: automated pipeline recovery"
        ),
    )

    print("Recovery patch committed.")

    # ---------------------------------------------------------
    # Open Pull Request
    # ---------------------------------------------------------

    pr_body = f"""
## Autonomous Pipeline Recovery

The Autonomous DevOps Pipeline Recovery Agent
detected and diagnosed a CI/CD failure.

### Proposed remediation

{remediation.summary}

### Reasoning

{remediation.reasoning}

### Risk

{remediation.risk}

### Validation

{"".join(f"- {step}\\n" for step in remediation.validation_steps)}

---

This pull request was automatically generated
after passing the safety policy engine.
"""

    pr = create_pull_request(
        branch_name=branch_name,
        title=(
            "fix: autonomous pipeline recovery"
        ),
        body=pr_body,
    )

    return {
        "branch": branch_name,
        "pull_request_number": pr["number"],
        "pull_request_url": pr["html_url"],
    }