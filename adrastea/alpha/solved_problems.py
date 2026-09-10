import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..config import config
from ..notifications.issue_manager import IssueCorrespondenceManager, AUTHORIZED_OPERATOR

logger = logging.getLogger("Adrastea.Alpha.SolvedProblems")

TARGET_REPOS = [
    "hardcode",
    "speech-flow",
    "market-research",
    "interpretive-interface",
    "distributed-content-management",
]


def get_repo_path(repo_name: str, workspace_dir: Optional[Path] = None) -> Path:
    """Resolve absolute local path for a target companion repository."""
    root = workspace_dir or config.companion_workspace_dir
    return root / repo_name


def inspect_repository(repo_name: str, workspace_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Solved Problem 1: Inspect repository environment, configuration files, git state,
    and available test frameworks deterministically.
    """
    repo_dir = get_repo_path(repo_name, workspace_dir)
    if not repo_dir.is_dir():
        return {
            "repo": repo_name,
            "exists": False,
            "error": f"Directory not found: {repo_dir}",
        }

    # Discover configuration files
    items = [p.name for p in repo_dir.iterdir()]
    has_adrastea_json = ".adrastea.json" in items
    adrastea_config: Dict[str, Any] = {}
    if has_adrastea_json:
        try:
            with open(repo_dir / ".adrastea.json", "r", encoding="utf-8") as f:
                adrastea_config = json.load(f)
        except Exception as e:
            logger.debug(f"Failed to read .adrastea.json in {repo_name}: {e}")

    # Discover project configs
    configs_found = []
    for cfg in [".adrastea.json", "pubspec.yaml", "pyproject.toml", "build.gradle.kts", "package.json", "requirements.txt", "setup.py"]:
        if cfg in items:
            configs_found.append(cfg)

    # Detect test runners
    test_runner = None
    if "python_driver.py" in items or "tests" in items or "test" in items:
        if "pubspec.yaml" in items:
            test_runner = "flutter test"
        elif any(f.endswith(".py") for f in items) or "tests" in items:
            test_runner = f'"{sys.executable}" -m unittest discover'
        elif "build.gradle.kts" in items:
            test_runner = "./gradlew test"

    # Git status
    git_branch = "unknown"
    is_clean = True
    last_commit = ""
    try:
        b_res = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if b_res.returncode == 0:
            git_branch = b_res.stdout.strip()

        st_res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if st_res.returncode == 0:
            is_clean = not bool(st_res.stdout.strip())

        log_res = subprocess.run(
            ["git", "log", "-n", "1", "--oneline"],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if log_res.returncode == 0:
            last_commit = log_res.stdout.strip()
    except Exception as e:
        logger.debug(f"Git status query failed for {repo_name}: {e}")

    return {
        "repo": repo_name,
        "exists": True,
        "path": str(repo_dir),
        "branch": git_branch,
        "is_clean": is_clean,
        "last_commit": last_commit,
        "configs": configs_found,
        "adrastea_config": adrastea_config,
        "test_runner": test_runner,
        "files_count": len(items),
    }


def fetch_repo_issues(repo_name: str, operator: str = AUTHORIZED_OPERATOR) -> Dict[str, Any]:
    """Solved Problem 2: Fetch open GitHub issues, evaluate wait states,
    and categorize issues ready for execution vs waiting for operator guidance.
    """
    github_repo = f"{operator}/{repo_name}" if "/" not in repo_name else repo_name
    mgr = IssueCorrespondenceManager(repo=github_repo)

    open_issues: List[Dict[str, Any]] = []
    try:
        res = subprocess.run(
            [
                "gh", "issue", "list",
                "--repo", github_repo,
                "--state", "open",
                "--json", "number,title,labels,updatedAt,comments,body,author",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        if res.returncode == 0 and res.stdout.strip():
            open_issues = json.loads(res.stdout)
    except Exception as e:
        return {"success": False, "repo": github_repo, "error": str(e)}

    actionable_issues: List[Dict[str, Any]] = []
    waiting_issues: List[Dict[str, Any]] = []

    for issue in open_issues:
        num = issue["number"]
        waiting, reason = mgr.is_waiting_for_user_response(num, issue_data=issue)
        issue_info = {
            "number": num,
            "title": issue.get("title", ""),
            "body": issue.get("body", ""),
            "comments_count": len(issue.get("comments", [])),
            "author": issue.get("author", {}).get("login", ""),
            "waiting": waiting,
            "reason": reason,
        }
        if waiting:
            waiting_issues.append(issue_info)
        else:
            actionable_issues.append(issue_info)

    return {
        "success": True,
        "repo": github_repo,
        "total_open": len(open_issues),
        "actionable_count": len(actionable_issues),
        "waiting_count": len(waiting_issues),
        "actionable_issues": actionable_issues,
        "waiting_issues": waiting_issues,
    }


def apply_code_patch(
    repo_name: str,
    file_modifications: Dict[str, str],
    workspace_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Solved Problem 3: Deterministically write or update files in a target repository.
    Validates syntax where appropriate (JSON, Python).
    """
    repo_dir = get_repo_path(repo_name, workspace_dir)
    if not repo_dir.is_dir():
        return {"success": False, "error": f"Repo dir does not exist: {repo_dir}"}

    written_files: List[str] = []
    errors: List[str] = []

    for rel_path, content in file_modifications.items():
        target_path = repo_dir / rel_path
        try:
            # Syntax validation
            if rel_path.endswith(".json"):
                json.loads(content)  # Ensure valid JSON syntax
            elif rel_path.endswith(".py"):
                compile(content, rel_path, "exec")  # Ensure valid Python syntax

            target_path.parent.mkdir(parents=True, exist_ok=True)
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(content)
            written_files.append(rel_path)
            logger.info(f"Solved Problems: Successfully wrote {rel_path} in {repo_name} ({len(content)} bytes)")
        except Exception as e:
            err_msg = f"Failed to patch {rel_path} in {repo_name}: {e}"
            logger.error(err_msg)
            errors.append(err_msg)

    return {
        "success": len(errors) == 0,
        "repo": repo_name,
        "written_files": written_files,
        "errors": errors,
    }


def run_tests(
    repo_name: str,
    test_cmd: Optional[str] = None,
    workspace_dir: Optional[Path] = None,
    timeout: int = 60,
) -> Dict[str, Any]:
    """Solved Problem 4: Deterministically run the test suite of a target repository."""
    repo_dir = get_repo_path(repo_name, workspace_dir)
    if not repo_dir.is_dir():
        return {"success": False, "error": f"Repo dir does not exist: {repo_dir}"}

    cmd = test_cmd
    if not cmd:
        # Auto-detect
        if (repo_dir / "test" / "test_python_driver.py").exists():
            cmd = f'"{sys.executable}" -m unittest test.test_python_driver'
        elif (repo_dir / "tests").exists():
            cmd = f'"{sys.executable}" -m unittest discover -s tests'
        elif (repo_dir / "test").exists() and (repo_dir / "pubspec.yaml").exists():
            cmd = "flutter test"
        else:
            cmd = f'"{sys.executable}" -c "print(\'No formal test suite configured for {repo_name}\')"'

    start_time = time.time()
    try:
        res = subprocess.run(
            cmd,
            cwd=str(repo_dir),
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        duration = round(time.time() - start_time, 2)
        return {
            "success": res.returncode == 0,
            "exit_code": res.returncode,
            "command": cmd,
            "duration": duration,
            "stdout": res.stdout[-1500:] if res.stdout else "",
            "stderr": res.stderr[-1500:] if res.stderr else "",
        }
    except Exception as e:
        return {
            "success": False,
            "exit_code": -1,
            "command": cmd,
            "duration": round(time.time() - start_time, 2),
            "error": str(e),
        }


def create_feature_branch_and_commit(
    repo_name: str,
    branch_name: str,
    commit_message: str,
    modified_files: List[str],
    workspace_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Solved Problem 5: Check out a feature branch, stage files, and commit."""
    repo_dir = get_repo_path(repo_name, workspace_dir)
    if not repo_dir.is_dir():
        return {"success": False, "error": f"Repo dir does not exist: {repo_dir}"}

    try:
        # Checkout branch (-B creates or resets cleanly)
        subprocess.run(
            ["git", "checkout", "-B", branch_name],
            cwd=str(repo_dir),
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        for f in modified_files:
            f_path = repo_dir / f
            if f_path.exists():
                subprocess.run(
                    ["git", "add", str(f_path)],
                    cwd=str(repo_dir),
                    check=True,
                    capture_output=True,
                    encoding="utf-8",
                    errors="replace",
                )

        commit_res = subprocess.run(
            ["git", "commit", "-m", commit_message],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return {
            "success": commit_res.returncode == 0 or "nothing to commit" in commit_res.stdout,
            "repo": repo_name,
            "branch": branch_name,
            "commit_output": commit_res.stdout.strip() or commit_res.stderr.strip(),
        }
    except Exception as e:
        return {"success": False, "repo": repo_name, "error": str(e)}


def push_and_open_pull_request(
    repo_name: str,
    branch_name: str,
    base_branch: str,
    pr_title: str,
    pr_body: str,
    assignee: str = AUTHORIZED_OPERATOR,
    workspace_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Solved Problem 6: Push feature branch and open a Pull Request on GitHub."""
    repo_dir = get_repo_path(repo_name, workspace_dir)
    github_repo = f"{assignee}/{repo_name}" if "/" not in repo_name else repo_name

    try:
        # Push branch
        push_res = subprocess.run(
            ["git", "push", "-u", "origin", branch_name, "--force"],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if push_res.returncode != 0:
            logger.warning(f"Push output for {repo_name}: {push_res.stderr.strip()}")

        # Check if PR already exists for branch
        list_pr = subprocess.run(
            ["gh", "pr", "list", "--repo", github_repo, "--head", branch_name, "--json", "number,url"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        if list_pr.returncode == 0 and list_pr.stdout.strip():
            existing = json.loads(list_pr.stdout)
            if existing:
                pr_url = existing[0]["url"]
                logger.info(f"Existing PR found for {branch_name} on {github_repo}: {pr_url}")
                return {"success": True, "repo": repo_name, "branch": branch_name, "pr_url": pr_url, "created": False}

        # Create new PR
        pr_cmd = [
            "gh", "pr", "create",
            "--repo", github_repo,
            "--head", branch_name,
            "--base", base_branch,
            "--title", pr_title,
            "--body", pr_body,
            "--assignee", assignee,
        ]
        pr_res = subprocess.run(
            pr_cmd,
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=25,
        )
        pr_url = pr_res.stdout.strip() if pr_res.returncode == 0 else ""
        return {
            "success": pr_res.returncode == 0,
            "repo": repo_name,
            "branch": branch_name,
            "base_branch": base_branch,
            "pr_url": pr_url,
            "created": True,
            "error": pr_res.stderr.strip() if pr_res.returncode != 0 else None,
        }
    except Exception as e:
        return {"success": False, "repo": repo_name, "error": str(e)}


def post_progress_and_pause(
    repo_name: str,
    issue_number: int,
    progress_summary: str,
    pr_url: Optional[str] = None,
    guidance_request: Optional[str] = None,
    operator: str = AUTHORIZED_OPERATOR,
) -> Dict[str, Any]:
    """Solved Problem 7: Post a structured progress comment to an issue thread,
    record the inquiry, and activate escalating wait backoff to pause for operator guidance.
    """
    github_repo = f"{operator}/{repo_name}" if "/" not in repo_name else repo_name
    mgr = IssueCorrespondenceManager(repo=github_repo)

    pr_line = f"\n- **Pull Request / Branch:** [{pr_url}]({pr_url})" if pr_url else ""
    guidance_block = (
        f"\n---\n\n### Guidance Needed from @{operator}\n"
        f"{guidance_request}\n\n"
        f"*Adrastea has paused subsequent notifications on this thread to await your review or direction.*"
        if guidance_request
        else f"\n---\n\n*Adrastea is paused on this thread awaiting review or further direction from @{operator}.*"
    )

    body = (
        f"### [Adrastea Progress Update]\n\n"
        f"**Repository:** `{github_repo}`\n"
        f"**Status:** Feature execution and validation completed for Issue #{issue_number}.\n"
        f"{pr_line}\n\n"
        f"#### What Was Implemented\n"
        f"{progress_summary}\n"
        f"{guidance_block}"
    )

    # Force post progress comment and escalate wait count
    res = mgr.post_response_to_issue(
        issue_number=issue_number,
        response_markdown=body,
        force=True,
        repo=github_repo,
    )
    mgr.record_adrastea_inquiry(issue_number)

    logger.info(f"Progress posted and pause activated on {github_repo} #{issue_number}: {res.get('details')}")
    return {
        "success": res.get("success", False),
        "repo": github_repo,
        "issue_number": issue_number,
        "paused": True,
        "details": res.get("details"),
    }


def loop_target_repositories_step(
    target_repos: Optional[List[str]] = None,
    workspace_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Solved Problem 8: The primary target repository looping program executed by Alpha.
    Inspects all target repos, gathers configuration files, checks open issues and wait states,
    and returns an actionable snapshot for Beta.
    """
    repos = target_repos or TARGET_REPOS
    repo_snapshots: Dict[str, Any] = {}
    actionable_queue: List[Dict[str, Any]] = []

    for repo in repos:
        env = inspect_repository(repo, workspace_dir)
        issues = fetch_repo_issues(repo)

        repo_snapshots[repo] = {
            "env": env,
            "issues": issues,
        }

        # If repo exists and has actionable issues, add to queue
        if env.get("exists") and issues.get("success"):
            for act_issue in issues.get("actionable_issues", []):
                actionable_queue.append({
                    "repo": repo,
                    "issue_number": act_issue["number"],
                    "title": act_issue["title"],
                    "body": act_issue["body"],
                    "configs": env.get("configs", []),
                    "adrastea_config": env.get("adrastea_config", {}),
                    "test_runner": env.get("test_runner"),
                })

    return {
        "timestamp": time.time(),
        "total_repos": len(repos),
        "actionable_queue_length": len(actionable_queue),
        "actionable_queue": actionable_queue,
        "snapshots": repo_snapshots,
    }


def cli_main():
    import sys
    action = sys.argv[1] if len(sys.argv) > 1 else "loop"
    repo = sys.argv[2] if len(sys.argv) > 2 else None

    if action == "inspect" and repo:
        env = inspect_repository(repo)
        issues = fetch_repo_issues(repo)
        print(f"REPO_LOOP: Repo={repo} | Actionable={issues.get('actionable_count')} | Waiting={issues.get('waiting_count')} | Tests={env.get('test_runner')}")
    elif action == "test" and repo:
        res = run_tests(repo)
        print(f"REPO_TEST: Repo={repo} | Success={res.get('success')} | Duration={res.get('duration')}s | ExitCode={res.get('exit_code')}")
    elif action == "loop":
        res = loop_target_repositories_step()
        print(f"TARGET_REPOS_LOOP: Total={res.get('total_repos')} | ActionableQueue={res.get('actionable_queue_length')}")
    else:
        print(f"Unknown action or missing repo: action={action}, repo={repo}")


if __name__ == "__main__":
    cli_main()

