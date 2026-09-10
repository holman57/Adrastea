import argparse
import datetime
import json
import logging
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ...config import config
from ..scheduler import ScheduledTask
from .base import BaseGoal

logger = logging.getLogger("Adrastea.Alpha.Goals.CompanionFeatureBuilder")

AUTHORIZED_OPERATOR = "holman57"

# Architectural specifications and objectives for each companion repository
COMPANION_REPO_SPECS: Dict[str, Dict[str, Any]] = {
    "distributed-content-management": {
        "github_repo": "holman57/distributed-content-management",
        "base_branch": "main",
        "title": "Autonomous Multi-Stream Content & Monetization Management",
        "objective": (
            "Autonomous system of spawning systems for multi-niche discovery, automated content "
            "generation pipelines, and multi-stream monetization governance."
        ),
        "tech_stack": "Python (pyproject.toml, rich, click, asyncio)",
        "core_components": ["src/dcm/", "tests/", "examples/"],
        "proposed_features": [
            "Multi-platform publisher connectors (WordPress, Substack, Medium REST API)",
            "Automated keyword and niche profitability scoring pipeline",
            "Content performance telemetry and monetization attribution tracker",
            "Markdown article generation with automated SEO metadata generation",
        ],
        "guidance_questions": [
            "Which content distribution channels should be prioritized first (e.g. static SSG markdown, headless WordPress, or newsletter syndication)?",
            "What monetization metrics or affiliate tracking parameters should be integrated into the publication pipeline?",
            "Are there specific niche domains you want targeted for initial automated discovery runs?",
        ],
    },
    "interpretive-interface": {
        "github_repo": "holman57/interpretive-interface",
        "base_branch": "master",
        "title": "Modern Android 15 Voice-First Communicative Interface",
        "objective": (
            "Voice-first communicative interface built with Kotlin and Jetpack Compose, "
            "real-time STT voice transcription, spoken TTS responses, and hands-free SMS audio reading."
        ),
        "tech_stack": "Kotlin, Gradle (build.gradle.kts), Android Jetpack Compose, Material3",
        "core_components": ["src/main/java/", "build.gradle.kts", "gradle/"],
        "proposed_features": [
            "Background audio service daemon with persistent notification controls",
            "Offline Vosk / Whisper STT integration for zero-cloud voice transcription",
            "Android broadcast receiver for hands-free incoming SMS transcription and audio reading",
            "Bluetooth media button / headset tap triggers for push-to-talk audio streaming",
        ],
        "guidance_questions": [
            "Would you like offline voice models (e.g., lightweight Vosk small model) bundled, or should it stream audio directly to speech-flow over IPC/WebSockets?",
            "What permissions and accessibility services should be registered for background SMS audio announcement?",
            "What UI theme or layout style do you envision for the primary voice visualizer on Android 15?",
        ],
    },
    "speech-flow": {
        "github_repo": "holman57/speech-flow",
        "base_branch": "main",
        "title": "Real-Time Speech Orchestration & Audio Bridge",
        "objective": (
            "Real-time speech orchestration and audio stream visualizer with live rolling word "
            "buffers, bidirectional IPC integration with Adrastea, and low-latency TTS voice playback."
        ),
        "tech_stack": "Python, PyQt6/PySide6, asyncio, sounddevice, Whisper/Vosk",
        "core_components": ["speech_flow/", "tests/"],
        "proposed_features": [
            "Voice Activity Detection (VAD) with customizable silence cutoff thresholds",
            "Push-to-talk system-wide keyboard hotkey handler",
            "Streaming chunked IPC socket bridge for low-latency Adrastea conversational responses",
            "Live wave visualizer with dynamic rolling word confidence indicator",
        ],
        "guidance_questions": [
            "What push-to-talk hotkey or trigger mechanism do you prefer on Windows (e.g. CapsLock, ScrollLock, or dedicated mouse button)?",
            "Which TTS voice model or audio engine should speech-flow bind to when outputting responses?",
            "What audio input sample rate and chunk duration are optimal for your microphone setup?",
        ],
    },
    "hardcode": {
        "github_repo": "holman57/hardcode",
        "base_branch": "main",
        "title": "Flashcard Programming Syntax Memorization System",
        "objective": (
            "A flashcard-style Question-and-Answer system for memorizing the syntax "
            "of common programming languages."
        ),
        "tech_stack": "Flutter / Dart (pubspec.yaml, lib/, test/), Python (python_driver.py)",
        "core_components": ["lib/", "test/", "db_backup.json", "python_driver.py"],
        "proposed_features": [
            "Expanded syntax question decks for modern languages: Rust, Go, TypeScript, Kotlin, and modern Python 3.12+",
            "Spaced Repetition Algorithm (SuperMemo SM-2) for optimized question scheduling",
            "Interactive command-line quiz and drill runner in python_driver.py",
            "Syntax highlighting and code snippet formatting within card presentations",
        ],
        "guidance_questions": [
            "Which programming languages or frameworks should be added to the syntax question database first?",
            "Would you like an interactive command-line study mode in `python_driver.py` for terminal drilling alongside the Flutter UI?",
            "Should question decks be synchronized via a remote JSON endpoint or kept locally inside `db_backup.json`?",
        ],
    },
    "market-research": {
        "github_repo": "holman57/market-research",
        "base_branch": "main",
        "title": "Web Crawler & Topic Scoring Engine",
        "objective": (
            "Web crawler and topic scoring engine for market research, topical inquiry, "
            "and content generation."
        ),
        "tech_stack": "Python (pyproject.toml, market_research/, tests/), BeautifulSoup4, asyncio",
        "core_components": ["market_research/", "tests/", "config.example.yaml"],
        "proposed_features": [
            "Multi-source search crawler supporting Google Trends, Hacker News, and Reddit feeds",
            "Automated executive research brief markdown generator",
            "Topic clustering and market competition scoring engine",
            "Scheduled automated inquiry runs with alert triggers for emerging market trends",
        ],
        "guidance_questions": [
            "What specific niche markets or industry domains should the default crawling scrapers monitor?",
            "What content format do you prefer for generated research summaries (e.g., bulleted executive briefs or full markdown dossiers)?",
            "Would you like integration with external search APIs (e.g. SerpAPI, Tavily) or purely headless HTML scraping?",
        ],
    },
}


def get_repo_path(repo_name: str, workspace_dir: Optional[Path] = None) -> Path:
    """Resolve absolute local path for a companion repository."""
    root = workspace_dir or config.companion_workspace_dir
    return root / repo_name


def analyze_companion_repo(repo_name: str, workspace_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Analyzes what a companion repo is attempting to accomplish, its current code state,
    and identifies feature upgrade opportunities.
    """
    repo_dir = get_repo_path(repo_name, workspace_dir)
    spec = COMPANION_REPO_SPECS.get(repo_name, {})
    exists = repo_dir.is_dir()

    if not exists:
        return {
            "repo": repo_name,
            "exists": False,
            "error": f"Repository directory not found at {repo_dir}",
            "spec": spec,
        }

    # Inspect files and structure
    items = [p.name for p in repo_dir.iterdir()]
    has_readme = "README.md" in items
    has_tests = (
        "tests" in items
        or "test" in items
        or (repo_dir / "src" / "test").exists()
    )

    # Git status
    git_branch = "unknown"
    is_clean = True
    commits_count = 0
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
        logger.debug(f"Git inspection failed for {repo_name}: {e}")

    return {
        "repo": repo_name,
        "exists": True,
        "path": str(repo_dir),
        "branch": git_branch,
        "is_clean": is_clean,
        "last_commit": last_commit,
        "has_readme": has_readme,
        "has_tests": has_tests,
        "spec": spec,
        "proposed_features": spec.get("proposed_features", []),
    }


def scan_and_converse_in_issues(
    repo_name: str,
    operator: str = AUTHORIZED_OPERATOR,
    auto_ask: bool = True
) -> Dict[str, Any]:
    """Scans open issues in the companion repository (holman57/<repo>), reads Luke's guidance,
    and posts targeted inquiries/responses when guidance is needed or provided.
    """
    spec = COMPANION_REPO_SPECS.get(repo_name)
    if not spec:
        return {"success": False, "error": f"Unknown repository spec: {repo_name}"}

    github_repo = spec["github_repo"]
    logger.info(f"Scanning issues for {github_repo}...")

    from ...notifications.issue_manager import IssueCorrespondenceManager
    mgr = IssueCorrespondenceManager(repo=github_repo)

    # Step 1: List open issues in this repo
    open_issues: List[Dict[str, Any]] = []
    try:
        res = subprocess.run(
            [
                "gh", "issue", "list",
                "--repo", github_repo,
                "--state", "open",
                "--json", "number,title,labels,updatedAt,comments,body,author"
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
        logger.warning(f"Failed to list issues for {github_repo}: {e}")
        return {"success": False, "repo": github_repo, "error": str(e)}

    # Step 2: Check for existing operator instructions or conversations
    operator_guidance: List[Dict[str, Any]] = []
    actions_taken: List[str] = []
    waiting_on_operator = False
    existing_guidance_issue: Optional[int] = None

    for issue in open_issues:
        num = issue["number"]
        title = issue.get("title", "")
        body = issue.get("body", "")
        author = issue.get("author", {}).get("login", "").strip().lower()
        comments = issue.get("comments", [])

        if "[adrastea" in title.lower() or "guidance" in title.lower() or "roadmap" in title.lower():
            existing_guidance_issue = num

        # Anti-spam check: is issue waiting on Luke's reply?
        waiting, reason = mgr.is_waiting_for_user_response(num, issue_data=issue)
        if waiting:
            waiting_on_operator = True
            continue

        # Case 1: Issue has comments
        if comments:
            last_comm = comments[-1]
            last_author = last_comm.get("author", {}).get("login", "").strip().lower()
            last_body = last_comm.get("body", "").strip()

            if mgr.is_adrastea_content(last_body, last_author):
                waiting_on_operator = True
                continue

            if last_author == operator.lower():
                operator_guidance.append({
                    "issue_number": num,
                    "title": title,
                    "directive": last_body,
                    "author": operator,
                })
                # Check if we should post a correspondence reply
                reply_md = (
                    f"**Autonomous Guidance Acknowledged for @{operator}**\n\n"
                    f"- **Target Repository:** `{github_repo}`\n"
                    f"- **Issue Thread:** #{num} (`{title}`)\n"
                    f"- **Received Guidance:**\n"
                    f"  > {last_body}\n\n"
                    f"- **System Alpha & Beta Execution Plan:**\n"
                    f"  1. Priority tuned for `{repo_name}` autonomous feature builder.\n"
                    f"  2. Ingested into long-term system memory.\n"
                    f"  3. Work will be staged on a dedicated branch and submitted via Pull Request.\n\n"
                    f"Standing by for further instructions."
                )
                post_res = mgr.post_response_to_issue(num, reply_md, force=True)
                if post_res.get("success"):
                    actions_taken.append(f"replied_to_guidance_#{num}")
                    logger.info(f"Replied to operator guidance on {github_repo} #{num}")
            elif last_author != operator.lower() and not mgr.is_adrastea_content(last_body, last_author):
                # External contributor commented
                mgr.post_contributor_pleasantry(num, last_author)
                actions_taken.append(f"sent_pleasantry_comment_#{num}")

        # Case 2: Issue has NO comments (newly opened issue)
        else:
            if author == operator.lower():
                is_adrastea_issue = mgr.is_adrastea_content(body, author)
                if not is_adrastea_issue:
                    operator_guidance.append({
                        "issue_number": num,
                        "title": title,
                        "directive": body or title,
                        "author": operator,
                    })
                    reply_md = (
                        f"**Autonomous Issue Ingestion & Response for @{operator}**\n\n"
                        f"- **Target Repository:** `{github_repo}`\n"
                        f"- **Issue:** #{num} (`{title}`)\n"
                        f"- **Directive / Topic:**\n"
                        f"  > {body or title}\n\n"
                        f"- **System Alpha & Beta Execution Plan:**\n"
                        f"  - Adopted this issue as an active objective for `{repo_name}`.\n"
                        f"  - Formulating implementation requirements and diagnostics.\n"
                        f"  - Updates and proposed PRs will be linked directly to this thread.\n\n"
                        f"Standing by for your steering."
                    )
                    post_res = mgr.post_response_to_issue(num, reply_md, force=True)
                    if post_res.get("success"):
                        actions_taken.append(f"replied_to_new_issue_#{num}")
                        logger.info(f"Replied to new issue #{num} on {github_repo}")
            elif author and author != operator.lower():
                # External user opened an issue
                mgr.post_contributor_pleasantry(num, author)
                actions_taken.append(f"sent_pleasantry_issue_#{num}")

    # Step 3: If no open issues or no guidance thread exists, create an initial guidance inquiry issue
    created_issue_num: Optional[int] = None
    if auto_ask and not existing_guidance_issue and not waiting_on_operator and not operator_guidance:
        logger.info(f"Opening architectural guidance and roadmap issue on {github_repo}...")
        questions_md = "\n".join(f"{i+1}. {q}" for i, q in enumerate(spec["guidance_questions"]))
        features_md = "\n".join(f"- [ ] **{f}**" for f in spec["proposed_features"])

        issue_title = f"[Adrastea RFC] Autonomous Feature Roadmap & Direction for {repo_name}"
        issue_body = (
            f"### [Adrastea RFC] Autonomous Feature Roadmap & Direction for `{repo_name}`\n\n"
            f"**Repository Objective:**\n"
            f"> {spec['objective']}\n\n"
            f"**Tech Stack:** `{spec['tech_stack']}`\n\n"
            f"---\n\n"
            f"### Proposed Autonomous Upgrade Features\n"
            f"{features_md}\n\n"
            f"---\n\n"
            f"### Guidance Questions for Luke (@{operator})\n"
            f"Adrastea is actively analyzing and building out upgrades for this repository. "
            f"To steer development and ensure changes align with your vision:\n\n"
            f"{questions_md}\n\n"
            f"---\n\n"
            f"### How to Steer\n"
            f"Reply directly to this issue with instructions, priorities, or answers. "
            f"Adrastea monitors this thread, will adopt your directives, and will open Pull Requests "
            f"assigned to you for significant new features."
        )

        try:
            create_res = subprocess.run(
                [
                    "gh", "issue", "create",
                    "--repo", github_repo,
                    "--title", issue_title,
                    "--body", issue_body,
                    "--assignee", operator,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
            )
            if create_res.returncode == 0:
                output_url = create_res.stdout.strip()
                match = re.search(r"/issues/(\d+)", output_url)
                created_issue_num = int(match.group(1)) if match else None
                actions_taken.append(f"created_guidance_issue_#{created_issue_num}")
                logger.info(f"Created guidance issue on {github_repo}: {output_url}")
        except Exception as e:
            logger.error(f"Failed to create guidance issue on {github_repo}: {e}")

    action_summary = ", ".join(actions_taken) if actions_taken else ("waiting_on_operator" if waiting_on_operator else "observed")
    return {
        "success": True,
        "repo": github_repo,
        "open_issues_count": len(open_issues),
        "existing_guidance_issue": existing_guidance_issue,
        "waiting_on_operator": waiting_on_operator,
        "operator_guidance": operator_guidance,
        "action_taken": action_summary,
        "actions_taken": actions_taken,
        "created_issue_number": created_issue_num,
    }


def create_feature_branch_and_pr(
    repo_name: str,
    branch_name: str,
    commit_message: str,
    pr_title: str,
    pr_body: str,
    modified_files: List[str],
    workspace_dir: Optional[Path] = None,
    assignee: str = AUTHORIZED_OPERATOR,
) -> Dict[str, Any]:
    """Creates a feature branch for significant upgrades, commits changes, pushes to GitHub,
    and opens a Pull Request assigned to Luke (@holman57).
    """
    repo_dir = get_repo_path(repo_name, workspace_dir)
    spec = COMPANION_REPO_SPECS.get(repo_name, {})
    base_branch = spec.get("base_branch", "main")
    github_repo = spec.get("github_repo", f"{assignee}/{repo_name}")

    if not repo_dir.is_dir():
        return {"success": False, "error": f"Repository directory not found at {repo_dir}"}

    logger.info(f"Opening feature branch '{branch_name}' on {repo_name} (Base: {base_branch})...")
    try:
        # 1. Checkout new feature branch
        subprocess.run(
            ["git", "checkout", "-b", branch_name],
            cwd=str(repo_dir),
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        # 2. Stage modified files
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

        # 3. Commit
        commit_res = subprocess.run(
            ["git", "commit", "-m", commit_message],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if commit_res.returncode != 0 and "nothing to commit" in commit_res.stdout:
            # Revert to base branch
            subprocess.run(
                ["git", "checkout", base_branch],
                cwd=str(repo_dir),
                capture_output=True,
                encoding="utf-8",
                errors="replace",
            )
            return {"success": False, "error": "Nothing to commit for feature branch"}

        # 4. Push feature branch to origin
        subprocess.run(
            ["git", "push", "-u", "origin", branch_name],
            cwd=str(repo_dir),
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        # 5. Open Pull Request assigned to Luke
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
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=25,
        )
        pr_url = pr_res.stdout.strip() if pr_res.returncode == 0 else ""

        # 6. Return back to base branch
        subprocess.run(
            ["git", "checkout", base_branch],
            cwd=str(repo_dir),
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )

        logger.info(f"Created Pull Request for {repo_name}: {pr_url} (Assigned to @{assignee})")
        return {
            "success": True,
            "repo": repo_name,
            "branch": branch_name,
            "base_branch": base_branch,
            "pr_url": pr_url,
            "assignee": assignee,
        }

    except Exception as e:
        logger.error(f"Failed creating feature branch/PR for {repo_name}: {e}")
        # Ensure we return to base branch if possible
        try:
            subprocess.run(["git", "checkout", base_branch], cwd=str(repo_dir), capture_output=True)
        except Exception:
            pass
        return {"success": False, "error": str(e)}


class CompanionFeatureBuilderGoal(BaseGoal):
    """Goal 6: Routinely loops through companion repositories, analyzes their architectures,
    builds out features and upgrades, pushes significant changes to PRs assigned to Luke,
    and converses in repository issues for guidance.
    """

    def __init__(self):
        super().__init__(
            goal_id="companion_feature_builder",
            name="Companion Repositories Feature Builder & Autonomous Upgrade",
            description=(
                "Routinely loops through distributed-content-management, interpretive-interface, "
                "speech-flow, hardcode, and market-research; analyzes what each repo is trying to accomplish; "
                "builds out features; opens Pull Requests assigned to Luke; and converses in repository issues for guidance."
            ),
            enabled=True,
            weight=1.4,
            interval_seconds=420.0,  # 7-minute cycle between companion repository passes
            parameters={
                "target_repos": [
                    "distributed-content-management",
                    "interpretive-interface",
                    "speech-flow",
                    "hardcode",
                    "market-research",
                ],
                "focus_repo": None,
                "auto_branch_prs": True,
                "assignee": AUTHORIZED_OPERATOR,
                "interactive_issues_enabled": True,
            },
        )
        self._current_index = 0

    def _select_target_repo(self) -> str:
        repos = self.parameters.get("target_repos", list(COMPANION_REPO_SPECS.keys()))
        focus = self.parameters.get("focus_repo")
        if focus and focus in repos:
            return focus
        directive_repo = self.parameters.get("directive_repo")
        if directive_repo:
            clean_repo = directive_repo.replace("holman57/", "").strip()
            if clean_repo in repos:
                return clean_repo
        if not repos:
            return "speech-flow"
        selected = repos[self._current_index % len(repos)]
        self._current_index += 1
        return selected

    def generate_tasks(self, context: Optional[Dict[str, Any]] = None) -> List[ScheduledTask]:
        now = (context.get("now") if context and "now" in context else time.time())
        tasks: List[ScheduledTask] = []
        base_priority = int(22 * self.weight)

        target_repo = self._select_target_repo()
        clean_repo_id = target_repo.replace("-", "_")

        # Task 1: Repository Architecture Analysis & Diagnostics
        cmd_analyze = (
            f'"{sys.executable}" -c '
            f'"from adrastea.alpha.goals.companion_feature_builder import analyze_companion_repo; '
            f'res = analyze_companion_repo(\'{target_repo}\'); '
            f'print(f\'COMPANION_ANALYSIS: Repo={target_repo} | Branch={{res.get(\"branch\")}} | '
            f'Clean={{res.get(\"is_clean\")}} | HasTests={{res.get(\"has_tests\")}} | HasReadme={{res.get(\"has_readme\")}}\')"'
        )
        tasks.append(
            ScheduledTask(
                task_id=f"feat_analyze_{clean_repo_id}_{int(now)}",
                command=cmd_analyze,
                priority=base_priority,
                interval_seconds=None,
                metadata={
                    "goal_id": self.goal_id,
                    "repo": target_repo,
                    "intent": "Companion Architecture Analysis",
                },
            )
        )

        # Task 2: Repository Issue Conversation & Guidance Scan
        if self.parameters.get("interactive_issues_enabled", True):
            cmd_issues = (
                f'"{sys.executable}" -c '
                f'"from adrastea.alpha.goals.companion_feature_builder import scan_and_converse_in_issues; '
                f'res = scan_and_converse_in_issues(\'{target_repo}\'); '
                f'print(f\'COMPANION_ISSUES: Repo={target_repo} | Action={{res.get(\"action_taken\")}} | '
                f'Waiting={{res.get(\"waiting_on_operator\")}} | Directives={{len(res.get(\"operator_guidance\", []))}}\')"'
            )
            tasks.append(
                ScheduledTask(
                    task_id=f"feat_issues_{clean_repo_id}_{int(now)}",
                    command=cmd_issues,
                    priority=base_priority + 2,
                    interval_seconds=None,
                    metadata={
                        "goal_id": self.goal_id,
                        "repo": target_repo,
                        "intent": "Repository Issue Conversation & Guidance Scan",
                    },
                )
            )

        self.mark_executed()
        return tasks


def main():
    parser = argparse.ArgumentParser(description="Adrastea Companion Repositories Feature Builder Utility")
    parser.add_argument("--repo", choices=list(COMPANION_REPO_SPECS.keys()), help="Target specific companion repository")
    parser.add_argument("--analyze", action="store_true", help="Analyze repository architecture and readiness")
    parser.add_argument("--scan-issues", action="store_true", help="Scan and converse on repository issues on GitHub")
    args = parser.parse_args()

    repo = args.repo or "speech-flow"

    if args.analyze:
        analysis = analyze_companion_repo(repo)
        print(json.dumps(analysis, indent=2))
    elif args.scan_issues:
        res = scan_and_converse_in_issues(repo)
        print(json.dumps(res, indent=2))
    else:
        # Default: Run full analysis and print summary
        analysis = analyze_companion_repo(repo)
        print(f"=== COMPANION REPO ANALYSIS: {repo} ===")
        print(f"Objective : {analysis.get('spec', {}).get('objective')}")
        print(f"Stack     : {analysis.get('spec', {}).get('tech_stack')}")
        print(f"Branch    : {analysis.get('branch')}")
        print(f"Clean     : {analysis.get('is_clean')}")
        print("Proposed Features:")
        for f in analysis.get("proposed_features", []):
            print(f"  - {f}")


if __name__ == "__main__":
    main()
