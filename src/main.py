import asyncio
import os

from src.tools.github_actions import (
    get_latest_failed_run,
    get_failed_jobs,
    get_run_logs,
    extract_log_text,
    extract_failure_evidence,
    get_previous_commit_sha,
    compare_commits,
    extract_diff_text,
    wait_for_recovery_validation,
)

from src.agents.rca_agent import analyze_failure

from src.agents.remediation_agent import generate_remediation

from src.policies.policy_engine import evaluate_remediation

from src.recovery.recovery_executor import (
    execute_recovery,
)

from src.incident.manager import create_incident

from src.notifications.slack import notify_incident_recovered

async def main():

    print("=" * 70)
    print("AUTONOMOUS DEVOPS PIPELINE RECOVERY AGENT")
    print("=" * 70)

    # ---------------------------------------------------------
    # STEP 1: Find latest failed GitHub Actions workflow
    # ---------------------------------------------------------

    print("\n[1] Looking for latest failed pipeline...")

    run = get_latest_failed_run()

    if not run:
        print("No failed pipeline found.")
        return

    print(f"Workflow : {run['name']}")
    print(f"Run ID   : {run['id']}")
    print(f"Branch   : {run['head_branch']}")
    print(f"Commit   : {run['head_sha'][:7]}")
    print(f"Status   : {run['conclusion']}")

    # ---------------------------------------------------------
    # STEP 2: Identify failed job and step
    # ---------------------------------------------------------

    print("\n[2] Identifying failed jobs...")

    failed_jobs = get_failed_jobs(run["id"])

    if not failed_jobs:
        print("No failed jobs found.")
        return

    for job in failed_jobs:
        print(f"Failed Job: {job['name']}")

        for step in job.get("steps", []):
            if step.get("conclusion") == "failure":
                print(f"Failed Step: {step['name']}")

    # ---------------------------------------------------------
    # STEP 3: Download GitHub Actions logs
    # ---------------------------------------------------------

    print("\n[3] Downloading pipeline logs...")

    zip_content = get_run_logs(run["id"])

    logs = extract_log_text(zip_content)

    # ---------------------------------------------------------
    # STEP 4: Extract relevant evidence
    # ---------------------------------------------------------

    print("\n[4] Extracting failure evidence...")

    failure_evidence = extract_failure_evidence(logs)

    print("\n--- FAILURE EVIDENCE ---")
    print(failure_evidence)

        # ---------------------------------------------------------
    # STEP 5: Inspect code changes
    # ---------------------------------------------------------

    print("\n[5] Inspecting code changes...")

    failed_commit = run["head_sha"]

    previous_commit = get_previous_commit_sha(failed_commit)

    git_diff = ""

    if previous_commit:

        comparison = compare_commits(
            previous_commit,
            failed_commit
        )

        git_diff = extract_diff_text(comparison)

        print("\n--- GIT DIFF ---")
        print(git_diff)

    else:
        print("Previous commit could not be determined.")

        
    # ---------------------------------------------------------
    # STEP 6: AI root cause analysis
    # ---------------------------------------------------------
    print("\n[6] Sending evidence to AutoGen RCA Agent...")
  
    rca_result = await analyze_failure(
    failure_evidence,
    git_diff
    )

    # ---------------------------------------------------------
    # STEP 6: Present RCA result
    # ---------------------------------------------------------

    print("\n" + "=" * 70)
    print("AI ROOT CAUSE ANALYSIS")
    print("=" * 70)

    print(rca_result.model_dump_json(indent=2))

    print("=" * 70)

    # ---------------------------------------------------------
    # STEP 7: Generate remediation proposal
    # ---------------------------------------------------------

    print("\n[7] Generating remediation proposal...")

    remediation_result = await generate_remediation(
        rca_result,
        git_diff,
    )

    print("\n" + "=" * 70)
    print("PROPOSED REMEDIATION")
    print("=" * 70)

    print(remediation_result.model_dump_json(indent=2))

    # ---------------------------------------------------------
    # STEP 8: Safety policy evaluation
    # ---------------------------------------------------------

    print("\n[8] Evaluating remediation against safety policy...")

    policy_result = evaluate_remediation(
        remediation_result
    )

    print("\n" + "=" * 70)
    print("SAFETY POLICY DECISION")
    print("=" * 70)

    print(policy_result.model_dump_json(indent=2))

    incident = create_incident(
        repository=f"{os.getenv('GITHUB_OWNER')}/{os.getenv('GITHUB_REPO')}",
        run=run,
        rca_result=rca_result,
        remediation_result=remediation_result,
        policy_result=policy_result,
    )

    print(f"\nIncident created: {incident.incident_id}")

    # ---------------------------------------------------------
    # STEP 9: Execute approved recovery
    # ---------------------------------------------------------

    print("\n[9] Evaluating automated recovery...")

    if policy_result.allowed_to_execute:

        print(
            "Policy allows automated recovery."
        )

        recovery_result = execute_recovery(
            remediation=remediation_result,
            policy=policy_result,
            failed_commit_sha=run["head_sha"],
            run_id=run["id"],
        )

        print()
        print("=" * 70)
        print("RECOVERY CREATED")
        print("=" * 70)

        print(
            f"Branch: "
            f"{recovery_result['branch']}"
        )

        print(
            f"PR: "
            f"{recovery_result['pull_request_number']}"
        )

        print(
            f"URL: "
            f"{recovery_result['pull_request_url']}"
        )

        incident.recovery_branch = recovery_result["branch"]
        incident.recovery_pr = recovery_result["pull_request_number"]
        incident.recovery_pr_url = recovery_result["pull_request_url"]

        incident.status = "VALIDATING"

    else:

        print(
            "Automated recovery not permitted."
        )

        print(
            f"Decision: {policy_result.decision}"
        )

    # ---------------------------------------------------------
    # STEP 10: Validate recovery
    # ---------------------------------------------------------

    print("\n[10] Waiting for recovery pipeline validation...")

    validation_result = wait_for_recovery_validation(
        recovery_result["branch"]
    )

    print()
    print("=" * 70)
    print("RECOVERY VALIDATION")
    print("=" * 70)

    print(
        f"Pipeline Run: {validation_result['run_id']}"
    )

    print(
        f"Conclusion: {validation_result['conclusion']}"
    )

    print(
        f"URL: {validation_result['url']}"
    )

    incident.validation_run_id = validation_result["run_id"]
    incident.validation_result = validation_result["conclusion"]

    if validation_result["conclusion"] == "success":

        incident.status = "RECOVERED"

        notify_incident_recovered(
            incident
        )

        print()
        print("✅ INCIDENT STATUS: RECOVERED")

    else:

        incident.status = "RECOVERY_FAILED"

        print()
        print("❌ INCIDENT STATUS: RECOVERY_FAILED")

if __name__ == "__main__":
    asyncio.run(main())

