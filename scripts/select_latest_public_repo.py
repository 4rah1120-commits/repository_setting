from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests


AUTOMATION_DIR = Path(__file__).resolve().parents[1]
STATE_PATH = AUTOMATION_DIR / "automation-state.json"


def write_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as output:
            output.write(f"{name}={value}\n")
    else:
        print(f"{name}={value}")


def save_state() -> None:
    state = {}
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    state[os.environ["SOURCE_REPOSITORY"]] = os.environ["SOURCE_SHA"]
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    if "--save" in sys.argv:
        save_state()
        return

    owner = os.environ["SOURCE_GITHUB_OWNER"]
    automation_repository = os.environ["AUTOMATION_REPOSITORY"].lower()
    response = requests.get(
        f"https://api.github.com/users/{owner}/repos",
        params={"type": "owner", "sort": "pushed", "per_page": 100},
        headers={"Accept": "application/vnd.github+json"},
        timeout=30,
    )
    response.raise_for_status()
    repositories = [
        repo
        for repo in response.json()
        if not repo["private"]
        and not repo["archived"]
        and not repo["fork"]
        and repo["full_name"].lower() != automation_repository
    ]
    if not repositories:
        raise RuntimeError("No public source repository found")

    previous = {}
    if STATE_PATH.exists():
        previous = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    force_run = os.environ.get("FORCE_RUN", "false").lower() == "true"

    selected = None
    for repository in repositories:
        branch = repository["default_branch"]
        commit_response = requests.get(
            f"https://api.github.com/repos/{repository['full_name']}/commits/{branch}",
            headers={"Accept": "application/vnd.github+json"},
            timeout=30,
        )
        commit_response.raise_for_status()
        sha = commit_response.json()["sha"]
        if force_run or previous.get(repository["full_name"]) != sha:
            selected = (repository, branch, sha)
            break

    if selected is None:
        write_output("changed", "false")
        print(json.dumps({"changed": False}))
        return

    repository, branch, sha = selected
    changed = True

    write_output("repository", repository["full_name"])
    write_output("branch", branch)
    write_output("sha", sha)
    write_output("changed", str(changed).lower())
    print(json.dumps({"repository": repository["full_name"], "branch": branch, "sha": sha, "changed": changed}))


if __name__ == "__main__":
    main()
