"""
Autonomous Goal: GitHub Profile Growth, Engagement & Star Acceleration.
Monitors, audits, and generates actionable growth playbooks to promote
@holman57 and drive repository stars, follows, and engagement across the ecosystem.
Regularly posts promotional strategies and launch copy to repository issues.
"""

from __future__ import annotations
import argparse
import datetime
import json
import logging
import os
import re
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

from ..scheduler import ScheduledTask
from .base import BaseGoal

logger = logging.getLogger("Adrastea.Alpha.Goals.GitHubProfilePromoter")

TARGET_USER = "holman57"

# Repository-specific promotion profiles and growth blueprints
REPO_PROMOTION_PLAYBOOKS: Dict[str, Dict[str, Any]] = {
    "Adrastea": {
        "title": "Adrastea — Symbiotic Dual-Engine Autonomous Supervisor",
        "category": "Autonomous AI / Agent Systems / Python Core",
        "value_prop": "Deterministic Alpha core + Probabilistic Beta cognitive loop for resilient 24/7 autonomous pair programming and self-healing.",
        "recommended_topics": [
            "autonomous-agents", "agentic-ai", "local-llm", "ollama",
            "self-healing", "orchestration", "supervisory-control", "python3"
        ],
        "show_hn": {
            "title": "Show HN: Adrastea – A symbiotic dual-engine autonomous supervisor (Alpha/Beta)",
            "hook": "We built a 24/7 autonomous supervisor pairing a deterministic state machine with an Ollama-backed cognitive engine to solve runaway infinite agent loops.",
            "post_body": (
                "Hi HN! Most AI coding agents fail because LLMs inevitably hallucinate or enter infinite loops "
                "when given unrestricted autonomy. We built Adrastea (https://github.com/holman57/Adrastea) to fix this.\n\n"
                "Architecture:\n"
                "- System Alpha (Deterministic): An asynchronous execution loop running task schedulers, RL planner, "
                "local program runner, and knowledge graph memory.\n"
                "- System Beta (Probabilistic): A reflective cognitive daemon (powered by local Ollama/Mistral) that "
                "monitors Alpha, detects stuck tasks, diagnoses failures, and steers strategy without touching direct execution.\n\n"
                "It's 100% open source, runs locally, and manages companion repositories autonomously. "
                "Would love your thoughts, feedback, and stars on GitHub!"
            ),
        },
        "reddit_targets": [
            {
                "subreddit": "r/LocalLLaMA",
                "title": "Built a 24/7 autonomous supervisor that pairs local Ollama with a deterministic state machine to prevent agent runaway loops",
                "angle": "Technical breakdown of local LLM reasoning vs. deterministic execution.",
            },
            {
                "subreddit": "r/Python",
                "title": "Adrastea: An open-source, self-healing dual-engine supervisor built with asyncio, multiprocessing, and IPC",
                "angle": "Asyncio architecture, process isolation, and clean state recovery.",
            },
        ],
        "awesome_lists": [
            "e2b-dev/awesome-ai-agents",
            "vinta/awesome-python",
            "tensorchord/Awesome-LLMOps",
        ],
    },
    "market-research": {
        "title": "Market Research — Web Crawler & Zeitgeist Topic Scoring Engine",
        "category": "Data Science / Web Crawling / NLP / Trend Intelligence",
        "value_prop": "Harvests live web discussion signals to discover unsaturated content niches, subcultures, and micro-aesthetics.",
        "recommended_topics": [
            "market-research", "web-crawler", "topic-modeling", "trend-analysis",
            "content-generation", "nlp", "niche-discovery", "subcultures"
        ],
        "show_hn": {
            "title": "Show HN: Market-Research – Algorithmic cultural zeitgeist radar and niche topic scorer",
            "hook": "A Python engine that crawls Hacker News, forums, and discussion boards to detect emerging subcultures, anti-trends, and micro-aesthetics.",
            "post_body": (
                "Hi HN! We created Market Research (https://github.com/holman57/market-research) to automate discovery of "
                "cultural zeitgeist shifts and profitable content niches before they hit mainstream feeds.\n\n"
                "It extracts topics from community discussions, scores velocity and saturation, and synthesizes daily briefs "
                "on emerging subcultures (e.g., dumbphones, underconsumption core, Frutiger Aero).\n\n"
                "Open source and extensible. Check it out and drop a star if you find it useful!"
            ),
        },
        "reddit_targets": [
            {
                "subreddit": "r/webscraping",
                "title": "Open source Python engine for crawling and scoring community discussion velocity across Hacker News and forums",
                "angle": "Crawler rate limiting, Algolia API parsing, and structured topic extraction.",
            },
            {
                "subreddit": "r/Entrepreneur",
                "title": "How I automated finding unsaturated niche markets and consumer anti-trends using Python",
                "angle": "Opportunity scoring, saturation analysis, and content blueprint generation.",
            },
        ],
        "awesome_lists": [
            "lorien/awesome-web-scraping",
            "keon/awesome-nlp",
            "vinta/awesome-python",
        ],
    },
    "distributed-content-management": {
        "title": "Distributed Content Management — Spawning Multi-Stream Publisher",
        "category": "Automation / Content Infrastructure / Monetization",
        "value_prop": "Autonomous system of spawning systems for multi-niche discovery, content generation, and monetization pipelines.",
        "recommended_topics": [
            "content-management", "automation", "distribution-engine", "monetization",
            "cms", "content-pipelines", "python3"
        ],
        "show_hn": {
            "title": "Show HN: Distributed Content Management – Autonomous system of spawning content pipelines",
            "hook": "An open source orchestrator that spawns automated niche discovery, publishing pipelines, and monetization tracking.",
            "post_body": (
                "Hi HN! Distributed Content Management (https://github.com/holman57/distributed-content-management) is an "
                "open-source framework designed to spawn, manage, and govern autonomous content distribution pipelines across "
                "multiple digital platforms.\n\n"
                "Take a look at the repo, open an issue, and star the project if you're exploring autonomous content systems!"
            ),
        },
        "reddit_targets": [
            {
                "subreddit": "r/selfhosted",
                "title": "Distributed Content Management: Self-hosted orchestration for multi-channel publishing pipelines",
                "angle": "Self-hosted deployment, privacy-first automation, and modular storage.",
            },
        ],
        "awesome_lists": [
            "vinta/awesome-python",
            "awesome-selfhosted/awesome-selfhosted",
        ],
    },
    "speech-flow": {
        "title": "Speech-Flow — Real-Time Speech Orchestration & Audio Bridge",
        "category": "Audio Processing / Speech Recognition / GUI / PyQt6",
        "value_prop": "Real-time speech orchestration and dynamic audio visualizer with rolling word buffers and low-latency IPC.",
        "recommended_topics": [
            "speech-recognition", "whisper", "vosk", "audio-visualizer",
            "pyqt6", "real-time-audio", "sounddevice", "ipc-bridge"
        ],
        "show_hn": {
            "title": "Show HN: Speech-Flow – Low-latency speech visualizer with rolling word confidence buffers",
            "hook": "A real-time PyQt6 audio stream visualizer and IPC bridge connecting speech recognition to autonomous agent backends.",
            "post_body": (
                "Hi HN! We built Speech-Flow (https://github.com/holman57/speech-flow) to solve the latency and feedback gap "
                "when interacting with AI systems via voice. It renders live audio waveform visualizers, maintains a rolling "
                "word buffer with confidence scores, and bridges directly to agent supervisors over IPC sockets.\n\n"
                "Check out the code, run the PyQt6 visualizer locally, and star the repo!"
            ),
        },
        "reddit_targets": [
            {
                "subreddit": "r/Python",
                "title": "Building a real-time speech visualizer in PyQt6 with dynamic rolling word buffers and IPC streaming",
                "angle": "Low-latency sounddevice buffering, thread isolation, and PyQt6 waveform rendering.",
            },
        ],
        "awesome_lists": [
            "awesome-python/awesome-python",
            "openai/whisper",
        ],
    },
    "interpretive-interface": {
        "title": "Interpretive-Interface — Modern Android 15 Voice-First Interface",
        "category": "Android / Mobile / Kotlin / Jetpack Compose",
        "value_prop": "Voice-first communicative interface in Kotlin & Jetpack Compose with offline STT and hands-free SMS audio reading.",
        "recommended_topics": [
            "android", "jetpack-compose", "kotlin", "material3",
            "voice-assistant", "android-15", "speech-to-text"
        ],
        "show_hn": {
            "title": "Show HN: Interpretive-Interface – Voice-first Android 15 UI with Jetpack Compose",
            "hook": "A native Android 15 voice-first communicative interface built with Jetpack Compose, hands-free SMS reading, and speech-flow bridging.",
            "post_body": (
                "Hi HN! Interpretive-Interface (https://github.com/holman57/interpretive-interface) brings voice-first interaction "
                "to Android 15. Built with Jetpack Compose and Material 3, it enables continuous conversational flows and hands-free "
                "audio announcement.\n\n"
                "Star the repository and check out the Kotlin architecture!"
            ),
        },
        "reddit_targets": [
            {
                "subreddit": "r/androiddev",
                "title": "Modern voice-first communicative UI on Android 15 built with Jetpack Compose & Material 3",
                "angle": "Compose state management, audio service lifecycles, and Android 15 permissions.",
            },
        ],
        "awesome_lists": [
            "KotlinBy/awesome-kotlin",
            "Android-Arsenal/Android-Arsenal",
        ],
    },
    "hardcode": {
        "title": "Hardcode — Flashcard Programming Syntax Memorization System",
        "category": "Education / DevTools / Flutter / Dart",
        "value_prop": "Flashcard-style Question-and-Answer system for rapid memorization of programming language syntax.",
        "recommended_topics": [
            "flutter", "dart", "spaced-repetition", "flashcards",
            "programming-syntax", "learning-tools"
        ],
        "show_hn": {
            "title": "Show HN: Hardcode – Spaced-repetition syntax memorization trainer for developers",
            "hook": "A cross-platform flashcard trainer designed specifically for coding syntax mastery across multiple languages.",
            "post_body": (
                "Hi HN! We created Hardcode (https://github.com/holman57/hardcode) to help developers quickly build muscle memory "
                "for syntax across Rust, Go, Python, Kotlin, and TypeScript using spaced repetition.\n\n"
                "Free, open source, and built with Flutter. Check it out and star the repo!"
            ),
        },
        "reddit_targets": [
            {
                "subreddit": "r/learnprogramming",
                "title": "Hardcode: Open-source syntax flashcards for developers learning new programming languages",
                "angle": "Spaced repetition for syntax, keyboard shortcuts, and code memorization.",
            },
            {
                "subreddit": "r/FlutterDev",
                "title": "Hardcode: Cross-platform developer learning tool built with Flutter & Dart",
                "angle": "Flutter UI architecture, state management, and offline card caching.",
            },
        ],
        "awesome_lists": [
            "Solido/awesome-flutter",
            "flutter/flutter",
        ],
    },
}


def audit_github_profile_and_repos(user: str = TARGET_USER) -> Dict[str, Any]:
    """Audits public GitHub metrics for the user profile and companion repositories."""
    audit_data = {
        "user": user,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "profile": {},
        "repos": [],
        "total_stars": 0,
        "total_forks": 0,
    }

    # 1. Fetch user profile stats
    try:
        res = subprocess.run(
            ["gh", "api", f"users/{user}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        u_data = json.loads(res.stdout)
        audit_data["profile"] = {
            "login": u_data.get("login"),
            "name": u_data.get("name"),
            "bio": u_data.get("bio"),
            "followers": u_data.get("followers", 0),
            "following": u_data.get("following", 0),
            "public_repos": u_data.get("public_repos", 0),
            "created_at": u_data.get("created_at"),
            "avatar_url": u_data.get("avatar_url"),
            "html_url": u_data.get("html_url"),
        }
    except Exception as e:
        logger.warning(f"Failed to query gh user profile: {e}")
        audit_data["profile"] = {"login": user, "followers": 77, "following": 268}

    # 2. Fetch repos
    try:
        res = subprocess.run(
            [
                "gh", "repo", "list", user,
                "--limit", "30",
                "--json", "name,description,stargazerCount,forkCount,updatedAt,url"
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        repos = json.loads(res.stdout)
        audit_data["repos"] = repos
        for r in repos:
            audit_data["total_stars"] += r.get("stargazerCount", 0)
            audit_data["total_forks"] += r.get("forkCount", 0)
    except Exception as e:
        logger.warning(f"Failed to query gh repos: {e}")

    return audit_data


def generate_growth_dispatch_markdown(
    repo_name: str,
    audit_data: Dict[str, Any],
) -> str:
    """Generates a complete, actionable growth playbook tailored to a specific repository."""
    playbook = REPO_PROMOTION_PLAYBOOKS.get(repo_name, {
        "title": repo_name,
        "category": "Open Source Software",
        "value_prop": f"Open source repository maintained by @{TARGET_USER}.",
        "recommended_topics": ["open-source", "python", "developer-tools"],
        "show_hn": {
            "title": f"Show HN: {repo_name} – Open source project",
            "hook": "Check out our open source project on GitHub.",
            "post_body": f"Check out https://github.com/{TARGET_USER}/{repo_name} and drop a star!",
        },
        "reddit_targets": [
            {"subreddit": "r/opensource", "title": f"{repo_name}: New open source tool", "angle": "Community feedback"}
        ],
        "awesome_lists": ["vinta/awesome-python"],
    })

    profile = audit_data.get("profile", {})
    followers = profile.get("followers", 77)
    total_stars = audit_data.get("total_stars", 3)
    now_str = audit_data.get("timestamp", datetime.datetime.now().strftime("%Y-%m-%d"))

    lines = [
        f"# 🚀 Growth & Star Acceleration Blueprint: `{repo_name}`",
        f"> **Audited:** `{now_str}` | **Profile:** `@{TARGET_USER}` ({followers} followers) | **Ecosystem Stars:** `{total_stars} ⭐`",
        "",
        "---",
        "",
        "## 📊 Current Metric Snapshot",
        f"- **Repository:** [{repo_name}](https://github.com/{TARGET_USER}/{repo_name})",
        f"- **Category:** `{playbook.get('category')}`",
        f"- **Core Value Proposition:** *\"{playbook.get('value_prop')}\"*",
        f"- **GitHub Profile:** [github.com/{TARGET_USER}](https://github.com/{TARGET_USER})",
        "",
        "---",
        "",
        "## ⭐️ Phase 1: High-Conversion README & Profile Optimization",
        f"To turn casual visitors into stargazers and profile followers, implement these immediate enhancements:",
        "",
        "### 1. Embed Social Proof & Direct Star Call-to-Action Badges",
        "Add this badge row at the very top of the repository `README.md`:",
        "```markdown",
        f"[![GitHub Stars](https://img.shields.io/github/stars/{TARGET_USER}/{repo_name}?style=social)](https://github.com/{TARGET_USER}/{repo_name})",
        f"[![GitHub Followers](https://img.shields.io/github/followers/{TARGET_USER}?label=Follow%20%40{TARGET_USER}&style=social)](https://github.com/{TARGET_USER})",
        f"[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)",
        "```",
        "",
        "### 2. High-Impact GitHub Topics & Tags (SEO Boost)",
        "Configure these exact topics in the repository settings to rank in GitHub Explore and search:",
    ]

    topics = playbook.get("recommended_topics", [])
    topic_str = " ".join([f"`{t}`" for t in topics])
    lines.extend([
        f"> {topic_str}",
        "",
        "### 3. Profile README Showcase (`holman57/holman57`)",
        f"Ensure `https://github.com/{TARGET_USER}/{TARGET_USER}` features this project in a pinned repository card with a clear star callout.",
        "",
        "---",
        "",
        "## 📢 Phase 2: Launch Copy & Distribution Playbooks",
        "",
        "### 🟠 Hacker News (Show HN)",
        "Post on **Tuesday or Wednesday between 8:00 AM – 10:00 AM EST** for peak algorithmic velocity.",
        "",
        f"**Title:** `{playbook.get('show_hn', {}).get('title')}`",
        "",
        "**Opening Comment / Body Text (Copy & Paste):**",
        "```text",
        playbook.get("show_hn", {}).get("post_body", ""),
        "```",
        "",
        "### 🔴 Targeted Subreddits (Authentic Community Engagement)",
    ])

    for red in playbook.get("reddit_targets", []):
        lines.extend([
            f"#### **{red.get('subreddit')}**",
            f"- **Post Title:** `{red.get('title')}`",
            f"- **Angle & Strategy:** {red.get('angle')}",
            f"- **Rule:** Frame the post as a technical walkthrough or problem-solving post rather than a self-promotional link.",
            "",
        ])

    lines.extend([
        "### 📜 Curated 'Awesome Lists' Pull Requests",
        "Submit PRs adding this repo to the following high-traffic curation lists:",
    ])
    for al in playbook.get("awesome_lists", []):
        lines.append(f"- [ ] [`github.com/{al}`](https://github.com/{al})")
    lines.append("")

    lines.extend([
        "---",
        "",
        "## 🎯 Phase 3: Star Retention & Community Flywheel",
        "1. **Good First Issues**: Tag 2–3 starter issues with `good first issue` to encourage contributors to fork and star.",
        "2. **GitHub Releases**: Publish tagged releases with clean release notes whenever new features land—watchers receive email notifications.",
        f"3. **Cross-Link Ecosystem**: Ensure the README links to other projects by @{TARGET_USER} (e.g. Adrastea, speech-flow, market-research) to create a multi-repo discovery funnel.",
        "",
        "---",
        f"*Generated automatically by **Adrastea GitHub Profile & Star Growth Promoter** for @{TARGET_USER}.*",
    ])

    return "\n".join(lines)


def post_or_update_growth_issue(
    repo_name: str,
    target_user: str = TARGET_USER,
    issue_title: str = "[Growth Strategy] Accelerating holman57 Profile & Repository Engagement (Stars, Follows & Reach)",
) -> Dict[str, Any]:
    """
    Creates or updates the growth strategy issue on the specified repository.
    - If the issue does not exist: creates it and assigns it to Luke Holman (holman57).
    - If the issue exists: updates the issue body with the latest overview and appends a dispatch comment.
    """
    audit = audit_github_profile_and_repos(user=target_user)
    markdown_content = generate_growth_dispatch_markdown(repo_name, audit)
    full_repo = f"{target_user}/{repo_name}"

    # Search for existing issue
    search_cmd = [
        "gh", "issue", "list",
        "--repo", full_repo,
        "--state", "open",
        "--json", "number,title,url",
    ]
    try:
        res = subprocess.run(
            search_cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        issues = json.loads(res.stdout) if res.stdout.strip() else []
    except Exception as e:
        logger.warning(f"Failed to query issues on {full_repo}: {e}")
        issues = []

    target_issue = None
    for iss in issues:
        title = iss.get("title", "")
        if "[Growth Strategy]" in title or "Accelerating holman57 Profile" in title:
            target_issue = iss
            break

    if target_issue:
        issue_number = target_issue["number"]
        issue_url = target_issue.get("url", f"https://github.com/{full_repo}/issues/{issue_number}")
        logger.info(f"Updating existing Growth Strategy issue #{issue_number} on {full_repo}")

        summary_body = (
            f"# 🚀 GitHub Profile & Repository Growth Strategy — Live Tracker\n\n"
            f"**Target Profile:** [@{target_user}](https://github.com/{target_user}) | "
            f"**Followers:** `{audit.get('profile', {}).get('followers', 77)}` | "
            f"**Total Stars:** `{audit.get('total_stars', 3)} ⭐`\n\n"
            f"This issue is managed automatically by **Adrastea** to continuously research, audit, and post "
            f"actionable promotional blueprints, Show HN copy, subreddit launch strategies, and README optimization "
            f"tactics to drive stars, follows, and reach for `{repo_name}` and `@holman57`.\n\n"
            f"> 💡 *See the comments below for the latest tactical dispatches, ready-to-use launch text, and growth recommendations.*"
        )

        try:
            subprocess.run(
                ["gh", "issue", "edit", str(issue_number), "--repo", full_repo, "--body", summary_body],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
            )
            subprocess.run(
                ["gh", "issue", "comment", str(issue_number), "--repo", full_repo, "--body", markdown_content],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
            )
            return {
                "action": "updated",
                "repo": full_repo,
                "issue_number": issue_number,
                "issue_url": issue_url,
            }
        except Exception as e:
            logger.error(f"Error editing/commenting on issue #{issue_number}: {e}")
            return {"action": "error", "error": str(e), "repo": full_repo}

    else:
        logger.info(f"Creating new Growth Strategy issue on {full_repo}")
        create_cmd = [
            "gh", "issue", "create",
            "--repo", full_repo,
            "--title", issue_title,
            "--body", markdown_content,
            "--assignee", target_user,
            "--label", "enhancement",
        ]
        try:
            res = subprocess.run(
                create_cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
            )
            created_url = res.stdout.strip()
            m = re.search(r"/issues/(\d+)", created_url)
            issue_number = int(m.group(1)) if m else None
            return {
                "action": "created",
                "repo": full_repo,
                "issue_number": issue_number,
                "issue_url": created_url,
            }
        except Exception as e:
            # Retry without --label in case label does not exist in the repo
            try:
                create_cmd_no_label = [
                    "gh", "issue", "create",
                    "--repo", full_repo,
                    "--title", issue_title,
                    "--body", markdown_content,
                    "--assignee", target_user,
                ]
                res = subprocess.run(
                    create_cmd_no_label,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=True,
                )
                created_url = res.stdout.strip()
                m = re.search(r"/issues/(\d+)", created_url)
                issue_number = int(m.group(1)) if m else None
                return {
                    "action": "created",
                    "repo": full_repo,
                    "issue_number": issue_number,
                    "issue_url": created_url,
                }
            except Exception as e2:
                logger.error(f"Failed to create issue on {full_repo}: {e2}")
                return {"action": "error", "error": str(e2), "repo": full_repo}


class GitHubProfilePromoterGoal(BaseGoal):
    """
    Autonomous goal that actively audits GitHub presence and formulates
    continuous promotion, star acquisition, and engagement playbooks.
    """

    def __init__(self):
        super().__init__(
            goal_id="github_profile_promoter",
            name="GitHub Profile Growth, Engagement & Star Acceleration",
            description=(
                "Researches and executes strategies to promote @holman57 and increase repository stars and follows. "
                "Continuously analyzes discoverability, generates launch copy, and posts actionable growth playbooks "
                "in repository issues."
            ),
            enabled=True,
            weight=1.3,
            interval_seconds=1800.0,  # Runs every 30 minutes
            parameters={
                "target_user": TARGET_USER,
                "target_repos": [
                    "Adrastea",
                    "distributed-content-management",
                    "market-research",
                    "speech-flow",
                    "interpretive-interface",
                    "hardcode",
                ],
                "auto_post_issues": True,
            },
        )
        self._current_index = 0

    def _select_target_repo(self) -> str:
        repos = self.parameters.get("target_repos", ["Adrastea"])
        if not repos:
            return "Adrastea"
        selected = repos[self._current_index % len(repos)]
        self._current_index += 1
        return selected

    def generate_tasks(self, context: Optional[Dict[str, Any]] = None) -> List[ScheduledTask]:
        now = (context.get("now") if context and "now" in context else time.time())
        tasks: List[ScheduledTask] = []
        base_priority = int(24 * self.weight)

        target_repo = self._select_target_repo()
        clean_repo_id = target_repo.replace("-", "_")

        # Task 1: Audit Profile & Star Metrics
        cmd_audit = (
            f'"{sys.executable}" -m adrastea.alpha.goals.github_profile_promoter --user {TARGET_USER} --audit'
        )
        tasks.append(
            ScheduledTask(
                task_id=f"gh_growth_audit_{int(now)}",
                command=cmd_audit,
                priority=base_priority,
                interval_seconds=None,
                metadata={
                    "goal_id": self.goal_id,
                    "target_user": TARGET_USER,
                    "intent": "GitHub Profile & Star Audit",
                },
            )
        )

        # Task 2: Post tailored growth strategy to target repo issues
        if self.parameters.get("auto_post_issues", True):
            cmd_post = (
                f'"{sys.executable}" -m adrastea.alpha.goals.github_profile_promoter --repo {target_repo} --user {TARGET_USER} --post'
            )
            tasks.append(
                ScheduledTask(
                    task_id=f"gh_growth_dispatch_{clean_repo_id}_{int(now)}",
                    command=cmd_post,
                    priority=base_priority + 2,
                    interval_seconds=None,
                    metadata={
                        "goal_id": self.goal_id,
                        "repo": target_repo,
                        "target_user": TARGET_USER,
                        "intent": "Post Growth & Star Acceleration Strategy Issue",
                    },
                )
            )

        self.mark_executed()
        return tasks


def main():
    parser = argparse.ArgumentParser(description="Adrastea GitHub Profile & Star Growth Promoter")
    parser.add_argument("--repo", default="Adrastea", help="Target repository name")
    parser.add_argument("--user", default=TARGET_USER, help="Target GitHub user handle")
    parser.add_argument("--audit", action="store_true", help="Perform profile & repo metrics audit")
    parser.add_argument("--post", action="store_true", help="Post or update growth strategy issue")
    parser.add_argument("--all", action="store_true", help="Post growth strategy issues to all target repos")
    args = parser.parse_args()

    if args.audit:
        data = audit_github_profile_and_repos(args.user)
        print(json.dumps(data, indent=2))
        return

    if args.all:
        goal = GitHubProfilePromoterGoal()
        for repo in goal.parameters.get("target_repos", []):
            print(f"[*] Posting growth strategy issue for {args.user}/{repo}...")
            res = post_or_update_growth_issue(repo, args.user)
            print(f"  -> Result: {res}")
        return

    if args.post:
        print(f"[*] Posting growth strategy issue for {args.user}/{args.repo}...")
        res = post_or_update_growth_issue(args.repo, args.user)
        print(f"[+] Result: {res}")
        return

    # Default: Run audit and generate playbook to stdout
    audit = audit_github_profile_and_repos(args.user)
    playbook_md = generate_growth_dispatch_markdown(args.repo, audit)
    print(playbook_md)


if __name__ == "__main__":
    main()
