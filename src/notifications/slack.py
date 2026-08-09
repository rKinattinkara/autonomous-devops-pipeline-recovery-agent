import os
import requests

from dotenv import load_dotenv

from src.models.incident import Incident


load_dotenv()


SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")


def send_slack_message(message: str):

    if not SLACK_WEBHOOK_URL or not SLACK_WEBHOOK_URL.startswith("https://"):
        print("Slack webhook not configured.")
        return

    response = requests.post(
        SLACK_WEBHOOK_URL,
        json={"text": message},
        timeout=30,
    )

    response.raise_for_status()


def notify_incident_recovered(
    incident: Incident,
):

    message = f"""
✅ *Autonomous Pipeline Recovery Successful*

*Incident:* {incident.incident_id}

*Repository:*
{incident.repository}

*Failed Workflow:*
{incident.failed_workflow}

*Root Cause:*
{incident.root_cause}

*Confidence:*
{incident.confidence:.0%}

*Remediation:*
{incident.remediation_summary}

*Safety Policy:*
{incident.policy_decision}

*Recovery Branch:*
{incident.recovery_branch}

*Recovery PR:*
<{incident.recovery_pr_url}|PR #{incident.recovery_pr}>

*Validation:*
{incident.validation_result}

*Status:*
RECOVERED
"""

    send_slack_message(message)