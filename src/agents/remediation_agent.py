import os

from dotenv import load_dotenv

from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient

from src.models.rca_result import RCAResult
from src.models.remediation_result import RemediationResult


load_dotenv()


async def generate_remediation(
    rca_result: RCAResult,
    git_diff: str,
) -> RemediationResult:

    model_client = OpenAIChatCompletionClient(
        model="gpt-4.1-mini",
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    remediation_agent = AssistantAgent(
        name="remediation_agent",

        model_client=model_client,

        output_content_type=RemediationResult,

        system_message="""
You are a senior DevOps and Site Reliability Engineer.

Your responsibility is to propose a safe remediation for a CI/CD failure.

You will receive:
- a structured root cause analysis
- the recent Git diff

Your job:

1. Propose the smallest reasonable fix.
2. Identify the file that should be modified.
3. Produce a proposed patch when evidence supports it.
4. Explain why the patch addresses the root cause.
5. Provide validation steps.
6. Assign risk as LOW, MEDIUM, or HIGH.
7. Decide whether human approval is required.

Important safety rules:

- DO NOT execute commands.
- DO NOT modify files.
- DO NOT push commits.
- DO NOT create branches.
- DO NOT create pull requests.
- DO NOT change secrets.
- DO NOT change IAM or permissions.
- Only propose remediation.
- Never invent files or code that were not present in the evidence.
- Prefer the smallest possible change.
""",
    )

    task = f"""
Generate a remediation proposal for this CI/CD failure.

ROOT CAUSE ANALYSIS:

{rca_result.model_dump_json(indent=2)}

RECENT GIT DIFF:

{git_diff}

Produce the safest minimal remediation supported by the evidence.
"""

    result = await remediation_agent.run(task=task)

    structured_result = result.messages[-1].content

    await model_client.close()

    return structured_result