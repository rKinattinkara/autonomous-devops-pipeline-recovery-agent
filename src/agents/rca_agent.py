import asyncio
import os

from dotenv import load_dotenv

from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient

from src.models.rca_result import RCAResult


load_dotenv()


async def analyze_failure(
    failure_evidence: str,
    git_diff: str = ""
) -> RCAResult:

    model_client = OpenAIChatCompletionClient(
        model="gpt-4.1-mini",
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    rca_agent = AssistantAgent(
        name="rca_agent",

        model_client=model_client,

        output_content_type=RCAResult,

        system_message="""
You are a senior Site Reliability Engineer specializing in CI/CD failure diagnosis.

Analyze ONLY the evidence provided.

Your responsibilities:

1. Identify the failure category.
2. Identify the failed component.
3. Determine the most probable root cause.
4. Cite concrete evidence from the logs.
5. Recommend the safest remediation.
6. Assign confidence between 0.0 and 1.0.
7. Assign risk as LOW, MEDIUM, or HIGH.

Rules:

- Never invent evidence.
- Do not assume information that is not present.
- If evidence is insufficient, lower confidence.
- Do not execute remediation.
- Do not modify code.
""",
    )

    task = f"""
Analyze the following CI/CD pipeline failure.

FAILURE EVIDENCE:

{failure_evidence}


RECENT CODE CHANGES:

{git_diff}


Determine whether the code changes are related to the pipeline failure.

Do not assume the code change caused the failure unless the evidence supports it.
"""

    result = await rca_agent.run(task=task)

    structured_result = result.messages[-1].content

    await model_client.close()

    return structured_result


async def main():

    sample_failure = """
FAILED demo_app/test_calculator.py::test_add

def test_add():
    assert add(2, 3) == 5

E   assert -1 == 5

1 failed, 3 passed
"""

    result = await analyze_failure(sample_failure)

    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())