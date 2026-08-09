import os
import requests
from dotenv import load_dotenv
import io
import zipfile
import time

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_OWNER = os.getenv("GITHUB_OWNER")
GITHUB_REPO = os.getenv("GITHUB_REPO")

BASE_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def get_latest_failed_run():
    url = f"{BASE_URL}/actions/runs"

    params = {
        "status": "failure",
        "per_page": 1,
    }

    response = requests.get(
        url,
        headers=HEADERS,
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    runs = response.json().get("workflow_runs", [])

    if not runs:
        return None

    return runs[0]


def get_failed_jobs(run_id):
    url = f"{BASE_URL}/actions/runs/{run_id}/jobs"

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    jobs = response.json().get("jobs", [])

    return [
        job
        for job in jobs
        if job.get("conclusion") == "failure"
    ]

def get_run_logs(run_id):
    url = f"{BASE_URL}/actions/runs/{run_id}/logs"

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    return response.content


def extract_log_text(zip_content):
    log_text = []

    with zipfile.ZipFile(io.BytesIO(zip_content)) as zip_file:
        for file_name in zip_file.namelist():
            if file_name.endswith(".txt"):
                with zip_file.open(file_name) as log_file:
                    content = log_file.read().decode(
                        "utf-8",
                        errors="replace",
                    )

                    log_text.append(
                        f"\n===== {file_name} =====\n{content}"
                    )

    return "\n".join(log_text)


def extract_failure_evidence(logs):
    keywords = [
        "FAILED",
        "ERROR",
        "AssertionError",
        "assert ",
        "Exception",
        "Traceback",
        "fatal:",
    ]

    lines = logs.splitlines()

    evidence = []

    for index, line in enumerate(lines):
        if any(keyword.lower() in line.lower() for keyword in keywords):

            start = max(0, index - 3)
            end = min(len(lines), index + 6)

            context = lines[start:end]

            evidence.extend(context)

    # Remove duplicates while preserving order
    evidence = list(dict.fromkeys(evidence))

    return "\n".join(evidence)


def get_commit(commit_sha):
    url = f"{BASE_URL}/commits/{commit_sha}"

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


def get_previous_commit_sha(commit_sha):
    commit = get_commit(commit_sha)

    parents = commit.get("parents", [])

    if not parents:
        return None

    return parents[0]["sha"]


def compare_commits(base_sha, head_sha):
    url = f"{BASE_URL}/compare/{base_sha}...{head_sha}"

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


def extract_diff_text(comparison):
    diff_sections = []

    for file in comparison.get("files", []):
        filename = file.get("filename")
        status = file.get("status")
        patch = file.get("patch")

        if not patch:
            continue

        diff_sections.append(
            f"""
FILE: {filename}
STATUS: {status}

{patch}
"""
        )

    return "\n".join(diff_sections)


def print_failure_summary():
    run = get_latest_failed_run()

    if not run:
        print("No failed workflow runs found.")
        return

    print("=" * 60)
    print("AUTONOMOUS DEVOPS PIPELINE RECOVERY AGENT")
    print("PIPELINE INSPECTOR")
    print("=" * 60)

    print(f"Repository : {GITHUB_OWNER}/{GITHUB_REPO}")
    print(f"Workflow   : {run['name']}")
    print(f"Run ID     : {run['id']}")
    print(f"Branch     : {run['head_branch']}")
    print(f"Commit     : {run['head_sha'][:7]}")
    print(f"Status     : {run['status']}")
    print(f"Conclusion : {run['conclusion']}")
    print(f"Run URL    : {run['html_url']}")

    failed_jobs = get_failed_jobs(run["id"])

    print()
    print("FAILED JOBS")
    print("-" * 60)

    for job in failed_jobs:
        print(f"Job: {job['name']}")

        for step in job.get("steps", []):
            if step.get("conclusion") == "failure":
                print(f"  Failed Step: {step['name']}")

    print()
    print("DOWNLOADING PIPELINE LOGS")
    print("-" * 60)

    zip_content = get_run_logs(run["id"])
    logs = extract_log_text(zip_content)

    failure_evidence = extract_failure_evidence(logs)

    print()
    print("FAILURE EVIDENCE")
    print("-" * 60)

    print(failure_evidence)

    print("=" * 60)


def get_workflow_runs_for_branch(branch_name):
    url = f"{BASE_URL}/actions/runs"

    params = {
        "branch": branch_name,
        "per_page": 10,
    }

    response = requests.get(
        url,
        headers=HEADERS,
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    return response.json().get("workflow_runs", [])


def wait_for_recovery_validation(
    branch_name: str,
    timeout_seconds: int = 300,
    poll_interval: int = 10,
):
    """
    Wait for GitHub Actions to finish validating
    the recovery branch / pull request.
    """

    start_time = time.time()

    while time.time() - start_time < timeout_seconds:

        runs = get_workflow_runs_for_branch(branch_name)

        if not runs:
            print("Waiting for recovery CI run to appear...")
            time.sleep(poll_interval)
            continue

        # Most recent run
        run = runs[0]

        print(
            f"Recovery CI: "
            f"status={run['status']} "
            f"conclusion={run['conclusion']}"
        )

        if run["status"] == "completed":

            return {
                "run_id": run["id"],
                "status": run["status"],
                "conclusion": run["conclusion"],
                "url": run["html_url"],
            }

        time.sleep(poll_interval)

    raise TimeoutError(
        "Timed out waiting for recovery pipeline validation."
    )

if __name__ == "__main__":
    print_failure_summary()