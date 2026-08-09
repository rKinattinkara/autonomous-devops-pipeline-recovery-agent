import base64
import os
import time

import requests
from dotenv import load_dotenv


load_dotenv()


GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_OWNER = os.getenv("GITHUB_OWNER")
GITHUB_REPO = os.getenv("GITHUB_REPO")

BASE_URL = (
    f"https://api.github.com/repos/"
    f"{GITHUB_OWNER}/{GITHUB_REPO}"
)

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def create_recovery_branch(
    base_commit_sha: str,
    run_id: int,
) -> str:

    branch_name = f"agent/recovery-{run_id}-{int(time.time())}"

    url = f"{BASE_URL}/git/refs"

    payload = {
        "ref": f"refs/heads/{branch_name}",
        "sha": base_commit_sha,
    }

    response = requests.post(
        url,
        headers=HEADERS,
        json=payload,
        timeout=30,
    )

    response.raise_for_status()

    return branch_name


def get_file(
    file_path: str,
    branch: str,
):

    url = f"{BASE_URL}/contents/{file_path}"

    params = {
        "ref": branch,
    }

    response = requests.get(
        url,
        headers=HEADERS,
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    return response.json()

def update_file(
    file_path: str,
    branch: str,
    new_content: str,
    current_file_sha: str,
    commit_message: str,
):

    url = f"{BASE_URL}/contents/{file_path}"

    encoded_content = base64.b64encode(
        new_content.encode("utf-8")
    ).decode("utf-8")

    payload = {
        "message": commit_message,
        "content": encoded_content,
        "sha": current_file_sha,
        "branch": branch,
    }

    response = requests.put(
        url,
        headers=HEADERS,
        json=payload,
        timeout=30,
    )

    response.raise_for_status()

    return response.json()

def decode_file_content(file_data) -> str:

    encoded_content = file_data["content"]

    return base64.b64decode(
        encoded_content
    ).decode("utf-8")


def create_pull_request(
    branch_name: str,
    title: str,
    body: str,
):

    url = f"{BASE_URL}/pulls"

    payload = {
        "title": title,
        "head": branch_name,
        "base": "main",
        "body": body,
    }

    response = requests.post(
        url,
        headers=HEADERS,
        json=payload,
        timeout=30,
    )

    response.raise_for_status()

    return response.json()