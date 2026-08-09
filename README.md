# Autonomous DevOps Pipeline Recovery Agent

An AI-powered agent that watches your GitHub Actions CI/CD pipeline, detects failures, diagnoses the root cause, proposes a targeted code fix, validates it through a rule-based safety policy, automatically opens a pull request with the fix, and confirms recovery by waiting for the new CI run to pass — all without human intervention.

---

## Table of Contents

- [What It Does](#what-it-does)
- [Architecture](#architecture)
- [Pipeline Walkthrough](#pipeline-walkthrough)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Setup](#setup)
- [Configuration](#configuration)
- [Running the Demo](#running-the-demo)
- [Key Design Decisions](#key-design-decisions)
- [Extending the Agent](#extending-the-agent)
- [Tech Stack](#tech-stack)

---

## What It Does

CI/CD failures interrupt developer flow. Most failures follow a recognisable pattern: a bad commit, a flipped operator, a wrong config value. This agent automates the recovery loop:

1. Detects the latest failed GitHub Actions workflow run via the REST API.
2. Downloads and parses the job logs to extract the failure signal.
3. Diffs the failing commit against its parent to surface the code change.
4. Sends both pieces of evidence to an AI agent for root-cause analysis.
5. Sends the RCA to a second AI agent that generates a unified-diff patch.
6. Runs the patch through a rule-based safety policy engine.
7. If approved, creates a recovery branch, applies the patch, commits it, and opens a PR.
8. Polls GitHub Actions until the new CI run on the recovery branch completes.
9. Marks the incident as `RECOVERED` and (optionally) posts a Slack notification.

The AI never executes code, accesses secrets, or merges — it only proposes a diff. The policy engine and GitHub's own CI are the safety gates.

---

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│                     GitHub Actions                          │
│         Push to main → CI pipeline runs → fails            │
│         GitHub Actions REST API exposes run + logs          │
└───────────────────────┬────────────────────────────────────┘
                        │ REST (read)
                        ▼
┌────────────────────────────────────────────────────────────┐
│               src/tools/github_actions.py                   │
│  • get_latest_failed_run()                                  │
│  • get_failed_jobs()                                        │
│  • get_run_logs()  →  extract_failure_evidence()           │
│  • compare_commits()  →  extract_diff_text()               │
│  • wait_for_recovery_validation()  (polls up to 300 s)     │
└───────────────────────┬────────────────────────────────────┘
                        │ failure evidence + git diff
                        ▼
┌────────────────────────────────────────────────────────────┐
│               src/agents/rca_agent.py                       │
│                                                             │
│  AutoGen AssistantAgent  (gpt-4.1-mini)                    │
│  Structured output → RCAResult                              │
│                                                             │
│  Fields: failure_category, failed_component, root_cause,   │
│          evidence[], recommended_action, confidence, risk   │
└───────────────────────┬────────────────────────────────────┘
                        │ RCAResult
                        ▼
┌────────────────────────────────────────────────────────────┐
│            src/agents/remediation_agent.py                  │
│                                                             │
│  AutoGen AssistantAgent  (gpt-4.1-mini)                    │
│  Structured output → RemediationResult                      │
│                                                             │
│  Fields: summary, target_file, proposed_change, patch,     │
│          reasoning, validation_steps[], risk,               │
│          requires_human_approval                            │
│                                                             │
│  patch is a standard unified diff (--- / +++ / @@ / +-)    │
└───────────────────────┬────────────────────────────────────┘
                        │ RemediationResult
                        ▼
┌────────────────────────────────────────────────────────────┐
│             src/policies/policy_engine.py                   │
│                                                             │
│  Rule-based — no AI.                                        │
│                                                             │
│  BLOCK if patch mentions: secret, password, token,          │
│    credential, iam, delete database, drop database,         │
│    destroy, terraform destroy                               │
│                                                             │
│  REVIEW if patch mentions: terraform, kubernetes,           │
│    deployment, helm, network, firewall, production          │
│                                                             │
│  ALLOW if target file is a low-risk extension               │
│    (.py, .js, .ts, .java, .cs) and no blocklist hit        │
│                                                             │
│  Output → PolicyResult                                      │
└───────────────────────┬────────────────────────────────────┘
                        │ PolicyResult (ALLOW)
                        ▼
┌────────────────────────────────────────────────────────────┐
│            src/incident/manager.py                          │
│  Incident created: INC-YYYYMMDD-HHMMSS                     │
│  Status: REMEDIATION_PROPOSED                               │
└───────────────────────┬────────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────────┐
│           src/recovery/recovery_executor.py                 │
│                                                             │
│  1. create_recovery_branch()                                │
│       agent/recovery-{run_id}-{unix_timestamp}              │
│                                                             │
│  2. get_file()  from recovery branch                        │
│                                                             │
│  3. apply_simple_patch()   ← patch_engine.py               │
│       Parses unified diff, locates the old block using      │
│       context lines to disambiguate duplicates, verifies    │
│       exactly one match, replaces it.                       │
│                                                             │
│  4. update_file()  — commit to recovery branch              │
│                                                             │
│  5. create_pull_request()  →  PR against main               │
│                                                             │
│  Incident status → VALIDATING                               │
└───────────────────────┬────────────────────────────────────┘
                        │ REST (write)
                        ▼
┌────────────────────────────────────────────────────────────┐
│                     GitHub Actions                          │
│         PR triggers CI on recovery branch                   │
│         Agent polls until run completes (max 5 min)        │
└───────────────────────┬────────────────────────────────────┘
                        │ conclusion: success / failure
                        ▼
┌────────────────────────────────────────────────────────────┐
│           src/notifications/slack.py  (optional)            │
│  Incident status → RECOVERED  or  RECOVERY_FAILED           │
│  Slack message posted if SLACK_WEBHOOK_URL is configured    │
└────────────────────────────────────────────────────────────┘
```

---

## Pipeline Walkthrough

Each numbered step maps directly to the `main()` function in `src/main.py`.

| Step | What happens |
|------|-------------|
| 1 | Poll GitHub API for the most recent failed workflow run on the repo |
| 2 | List jobs in that run; surface the failed job name and failed step name |
| 3 | Download the zipped run logs; unzip in memory; concatenate all log text |
| 4 | Extract the failure-relevant portion of the logs (error lines, assertion output) |
| 5 | Compare the failing commit to its parent; format as a git diff |
| 6 | RCA Agent receives logs + diff → returns structured `RCAResult` |
| 7 | Remediation Agent receives `RCAResult` + diff → returns structured `RemediationResult` with unified-diff patch |
| 8 | Policy Engine evaluates the patch against keyword blocklists → `PolicyResult` |
| 8b | `Incident` record created in memory, status `REMEDIATION_PROPOSED` |
| 9 | If `PolicyResult.allowed_to_execute`: create branch → apply patch → commit → open PR; incident → `VALIDATING` |
| 10 | Poll Actions API until recovery CI run completes; incident → `RECOVERED` or `RECOVERY_FAILED`; Slack notification on success |

---

## Project Structure

```
autonomous-devops-pipeline-recovery-agent/
│
├── .env.example                   # Copy to .env and fill in your credentials
├── .gitignore
├── requirements.txt
│
├── demo_app/                      # Intentionally broken calculator app
│   ├── calculator.py              # add() returns a - b (the bug the agent fixes)
│   └── test_calculator.py         # pytest suite that catches the bug
│
├── .github/
│   └── workflows/
│       └── ci.yml                 # Demo CI: checkout → install pytest → run tests
│
└── src/
    ├── main.py                    # Top-level async orchestrator (10 steps)
    │
    ├── agents/
    │   ├── rca_agent.py           # AutoGen agent: evidence + diff → RCAResult
    │   └── remediation_agent.py   # AutoGen agent: RCAResult → RemediationResult
    │
    ├── models/
    │   ├── rca_result.py          # Pydantic: structured RCA output schema
    │   ├── remediation_result.py  # Pydantic: structured remediation + patch schema
    │   ├── policy_result.py       # Pydantic: policy decision schema
    │   └── incident.py            # Pydantic: full incident lifecycle record
    │
    ├── policies/
    │   └── policy_engine.py       # Rule-based safety gate — no AI
    │
    ├── recovery/
    │   ├── recovery_executor.py   # Orchestrates branch → patch → commit → PR
    │   └── patch_engine.py        # Unified-diff parser and file patcher
    │
    ├── tools/
    │   ├── github_actions.py      # GitHub Actions REST API (read: runs, logs, diffs)
    │   └── github_recovery.py     # GitHub REST API (write: branches, files, PRs)
    │
    ├── incident/
    │   └── manager.py             # Creates and populates the Incident record
    │
    └── notifications/
        └── slack.py               # Optional Slack incoming webhook notification
```

---

## Prerequisites

- Python 3.11 or later
- A GitHub account with a repository that has GitHub Actions enabled
- An OpenAI API key (the agents use `gpt-4.1-mini`)
- (Optional) A Slack incoming webhook URL for recovery notifications

---

## Setup

### 1. Fork or clone this repository

```bash
git clone https://github.com/YOUR_USERNAME/autonomous-devops-pipeline-recovery-agent.git
cd autonomous-devops-pipeline-recovery-agent
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Create your `.env` file

```bash
cp .env.example .env
```

Open `.env` and fill in your values (see [Configuration](#configuration)).

### 5. Create a GitHub Personal Access Token

Go to **GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.

Set the resource owner to your account and select your forked repository. Grant these permissions:

| Permission | Level |
|---|---|
| Actions | Read |
| Contents | Read and write |
| Pull requests | Read and write |
| Workflows | Read |

Paste the generated token as `GITHUB_TOKEN` in your `.env`.

---

## Configuration

All configuration lives in `.env`. This file is in `.gitignore` and must never be committed.

| Variable | Required | Description |
|---|---|---|
| `GITHUB_TOKEN` | Yes | Fine-grained PAT with Actions / Contents / Pull requests / Workflows access |
| `GITHUB_OWNER` | Yes | GitHub username or organisation that owns the repository |
| `GITHUB_REPO` | Yes | Repository name (without the owner prefix) |
| `OPENAI_API_KEY` | Yes | OpenAI API key — used by both the RCA and Remediation agents |
| `SLACK_WEBHOOK_URL` | No | Slack incoming webhook URL; leave as placeholder to disable notifications |

---

## Running the Demo

The demo scenario is baked into the repository: `demo_app/calculator.py` contains an intentional bug — `add()` returns `a - b` instead of `a + b`. When any commit is pushed to `main`, the GitHub Actions CI pipeline runs pytest and fails. The agent detects this failure, diagnoses it, patches it, opens a PR, and waits for CI to pass on the recovery branch.

### Step 1 — Trigger the failing pipeline

```bash
git commit --allow-empty -m "trigger: demo pipeline failure"
git push origin main
```

Wait about 30–60 seconds for the GitHub Actions run to appear as **failed** in your repository's Actions tab.

### Step 2 — Run the recovery agent

```bash
python -m src.main
```

The agent will print each step as it runs:

```
======================================================================
AUTONOMOUS DEVOPS PIPELINE RECOVERY AGENT
======================================================================

[1] Looking for latest failed pipeline...
Workflow : Demo CI Pipeline
Run ID   : 31261807539
Branch   : main
Commit   : 2690529
Status   : failure

[2] Identifying failed jobs...
Failed Job: Run Python Tests
Failed Step: Run Tests

[3] Downloading pipeline logs...

[4] Extracting failure evidence...
--- FAILURE EVIDENCE ---
assert add(2, 3) == 5
E       assert -1 == 5

[5] Inspecting code changes...
--- GIT DIFF ---
-    return a + b
+    return a - b

[6] Sending evidence to AutoGen RCA Agent...
...
[7] Generating remediation proposal...
...
[8] Evaluating remediation against safety policy...
Decision: ALLOW

Incident created: INC-20260808-143200

[9] Evaluating automated recovery...
Created recovery branch: agent/recovery-31261807539-1786235096
Patch validated.
Recovery patch committed.
PR: https://github.com/YOUR_USERNAME/autonomous-devops-pipeline-recovery-agent/pull/1

[10] Waiting for recovery pipeline validation...
Recovery CI: status=in_progress conclusion=None
Recovery CI: status=completed conclusion=success

✅ INCIDENT STATUS: RECOVERED
```

### Step 3 — Review the pull request

Open the PR URL printed in the output. You will see:

- The exact one-line diff (`return a - b` → `return a + b`)
- The full RCA reasoning written by the AI
- Validation steps and risk assessment
- A passing CI check on the recovery branch

You can merge the PR to restore `main` to a clean state, ready for the next demo run.

---

## Key Design Decisions

### AI agents produce structured output, not free text

Both agents use AutoGen's `output_content_type` to constrain responses to a Pydantic schema (`RCAResult`, `RemediationResult`). There is no parsing of markdown or manual JSON extraction — the output is a validated, typed Python object. If the model produces something that doesn't match the schema, AutoGen rejects and retries automatically.

### The policy engine contains no AI

The component that decides whether to write code to GitHub is deterministic keyword matching. This is intentional: the safety gate must be auditable, predictable, and testable without a language model. The AI proposes; the rules decide.

### The patch engine uses context lines, not line numbers

The agent receives a standard unified diff from the AI. Rather than relying on the `@@ -N,M @@` line numbers (which can drift as files change), the patch engine builds a search block from `context_before + removed_lines + context_after` and requires that exact block to appear exactly once in the file. This is both safer and more robust than line-number-based patching.

### Recovery validation comes from GitHub, not the AI

After opening the recovery PR, the agent polls the GitHub Actions API for the new CI run on the recovery branch. The `conclusion` — `success` or `failure` — is determined by whether pytest actually passed. The agent never self-certifies that its fix worked.

### Branch naming includes a Unix timestamp

Recovery branches are named `agent/recovery-{run_id}-{unix_timestamp}`. The timestamp ensures uniqueness across multiple agent runs against the same failed workflow run, preventing 422 conflicts from the GitHub API.

### Secrets are read exclusively from environment variables

No credentials appear in source code. All tokens and API keys are loaded via `python-dotenv`. The Slack notifier verifies the webhook URL starts with `https://` before making any network request, so unconfigured placeholder values are silently skipped.

---

## Extending the Agent

### Change the AI model

Both agents use `gpt-4.1-mini`. Change the `model=` argument in `rca_agent.py` and `remediation_agent.py` to any model supported by `autogen-ext`'s `OpenAIChatCompletionClient`, including Azure OpenAI endpoints.

### Tighten or relax the policy

Edit the blocklist and review-list keyword arrays in `src/policies/policy_engine.py`. The logic is plain Python — no configuration files or DSLs to learn.

### Add more notification channels

Add a new function to `src/notifications/` following the same pattern as `slack.py`, then call it from `main.py` alongside `notify_incident_recovered`.

### Persist incidents

The `Incident` Pydantic model is currently held in memory for the duration of a run. Add a save step after each status transition to write to a JSON file, a database, or a third-party incident management API (PagerDuty, OpsGenie, etc.).

### Watch multiple repositories

Wrap `main()` in a loop over a list of `(owner, repo)` pairs, passing each pair as environment overrides, or run the agent as a scheduled workflow using GitHub Actions itself.

### Auto-merge on high-confidence recoveries

After `wait_for_recovery_validation()` returns `success`, call the GitHub Merge API to merge the PR automatically. Add a guard in the policy engine — for example, only auto-merge when `RCAResult.confidence >= 0.95` and `risk == "LOW"`.

---

## Tech Stack

| Component | Technology |
|---|---|
| AI agents | [AutoGen AgentChat](https://microsoft.github.io/autogen/) (`autogen-agentchat`) |
| LLM | OpenAI `gpt-4.1-mini` via `autogen-ext` |
| Structured output | [Pydantic v2](https://docs.pydantic.dev/) |
| GitHub integration | GitHub REST API v2022-11-28 via `requests` |
| CI/CD target | GitHub Actions |
| Notifications | Slack Incoming Webhooks |
| Configuration | `python-dotenv` |
| Demo test suite | pytest |
| Runtime | Python 3.11+ / asyncio |
