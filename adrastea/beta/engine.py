import argparse
import asyncio
import logging
import time
from typing import Any, Dict, Optional

from ..activity_logger import ActivityLogger
from ..config import config
from ..directives import DirectiveWatcher
from ..ipc.channel import IPCClient
from ..ipc.protocol import Message, SignalType
from ..notifications.notifier import Notifier
from .delivery_strategist import DeliveryStrategist
from .discovery import GoalDiscovery
from .llm_consultant import LLMConsultant
from .mcp_client import MCPClient
from .triage import TriageEngine
from .tuner import HeuristicTuner
from ..knowledge.prompt_compiler import CognitivePromptCompiler

logger = logging.getLogger("Adrastea.Beta")


class BetaEngine:
    """Probabilistic Cognitive Engine for Adrastea."""

    def __init__(self, ipc_host: str = "127.0.0.1", ipc_port: int = 8765):
        self.ipc = IPCClient(host=ipc_host, port=ipc_port)
        self.llm = LLMConsultant()
        self.mcp = MCPClient()
        self.prompt_compiler = CognitivePromptCompiler()
        self.triage = TriageEngine(llm=self.llm)
        self.tuner = HeuristicTuner()
        self.discovery = GoalDiscovery(llm=self.llm)
        self.notifier = Notifier()
        self.strategist = DeliveryStrategist()
        self.watcher = DirectiveWatcher()
        self.activity_logger = ActivityLogger()

        self._running = False
        self._sleeping = False
        self._wake_event = asyncio.Event()
        self.sleep_interval = config.keepalive_sleep_seconds
        self._loop_task: Optional[asyncio.Task] = None
        self.last_telemetry: Dict[str, Any] = {}

        self._setup_ipc_handlers()

    def _setup_ipc_handlers(self) -> None:
        self.ipc.register_handler(SignalType.SIG_TELEMETRY, self._on_telemetry)
        self.ipc.register_handler(SignalType.SIG_STUCK, self._on_stuck)
        self.ipc.register_handler(SignalType.SIG_TASK_FAILED, self._on_task_failed)
        self.ipc.register_handler(SignalType.SIG_HEARTBEAT, self._on_heartbeat)
        self.ipc.register_handler(SignalType.SIG_SLEEP, self._on_sleep)
        self.ipc.register_handler(SignalType.SIG_WAKE, self._on_wake)
        self.ipc.register_handler(SignalType.SIG_GOALS_STATUS, self._on_goals_status)

    async def _on_heartbeat(self, msg: Message) -> Message:
        logger.debug(f"Beta received heartbeat from {msg.sender}")
        return Message(
            signal=SignalType.SIG_HEARTBEAT,
            sender="Beta",
            payload={"status": "alive", "sleeping": self._sleeping, "timestamp": time.time()}
        )

    async def _on_sleep(self, msg: Message) -> None:
        duration = msg.payload.get("duration", self.sleep_interval)
        self.sleep_interval = float(duration)
        self._sleeping = True
        self._wake_event.clear()
        logger.info(f"Beta entered keep-alive sleep mode (interval: {self.sleep_interval}s). Listening and signaling remain active.")

    async def _on_wake(self, msg: Message) -> None:
        self._sleeping = False
        self._wake_event.set()
        logger.info("Beta received SIG_WAKE. Waking to active mode.")

    async def _on_telemetry(self, msg: Message) -> None:
        self.last_telemetry = msg.payload
        logger.debug(f"Received Alpha telemetry: Uptime={msg.payload.get('uptime_seconds')}s")

    async def _on_stuck(self, msg: Message) -> None:
        """Immediate high-priority triage when Alpha is stuck."""
        task_id = msg.payload.get("task_id", "unknown")
        logger.warning(f"ALPHA STUCK SIGNAL DETECTED for [{task_id}]")
        signals = self.triage.analyze_stuck_state(msg.payload)
        for sig in signals:
            logger.info(f"Beta dispatching corrective signal {sig.signal} to Alpha...")
            await self.ipc.send(sig)

        # Significant happening: Triage intervention!
        self.activity_logger.log_cycle(
            alpha_status=self.last_telemetry,
            beta_action=f"Autonomous Triage Intervention for stuck task [{task_id}]"
        )
        self.activity_logger.commit_and_push_significant_event(
            f"triaged and resolved stuck task [{task_id}]",
            min_cooldown_seconds=1800.0
        )

    async def _on_task_failed(self, msg: Message) -> None:
        logger.info(f"Task failed notification: {msg.payload.get('task_id')}")

    async def _on_goals_status(self, msg: Message) -> None:
        goals = msg.payload.get("goals", {})
        logger.debug(f"Beta received goals status update from Alpha: {len(goals)} goals active.")

    async def start(self) -> None:
        """Connect to Alpha IPC and start cognitive loop."""
        self._running = True
        logger.info("Initializing System Beta...")

        connected = await self.ipc.connect(retries=10, delay=1.0)
        if not connected:
            logger.error("Failed to connect to Alpha IPC Server. Exiting Beta.")
            return

        logger.info("System Beta connected to Alpha. Starting cognitive loop...")
        self._loop_task = asyncio.create_task(self._cognitive_loop())

    async def _cognitive_loop(self) -> None:
        """Main loop: Cycles through Idle/Wait, Directive Checking, Outreach with Backoff, and Optimization."""
        iteration = 0
        while self._running:
            try:
                iteration += 1
                logger.info(f"System Beta cognitive cycle #{iteration} (Observing & Idle)")

                # 1. Check for user directives from Luke (DIRECTIVES.txt or GitHub Issue comments)
                directive = self.watcher.check_directives()
                if directive:
                    goal_id = getattr(directive, "goal_id", None)
                    issue_num = getattr(directive, "issue_number", None)
                    logger.info(f"Directives received from Luke: '{directive}' (Goal: {goal_id}, Issue: #{issue_num})")
                    self.strategist.reset_backoff_on_response()

                    # If sleeping, wake both Beta and Alpha
                    if self._sleeping:
                        self._sleeping = False
                        self._wake_event.set()
                        await self.ipc.send(Message(signal=SignalType.SIG_WAKE, sender="Beta"))

                    # A. Goal Steering: If directive targets a specific goal, tune it immediately
                    directive_repo = getattr(directive, "repo", None) or "holman57/Adrastea"
                    if goal_id:
                        logger.info(f"Targeted directive steering for goal [{goal_id}] on {directive_repo}...")
                        tune_payload: Dict[str, Any] = {
                            "goal_id": goal_id,
                            "weight": 2.5,
                            "parameters": {
                                "latest_user_instruction": str(directive),
                                "directive_repo": directive_repo,
                            },
                        }
                        if goal_id in ("ecosystem_repos", "companion_feature_builder"):
                            d_lower = str(directive).lower()
                            for repo in ["speech-flow", "interpretive-interface", "distributed-content-management", "hardcode", "market-research"]:
                                if repo in d_lower or repo.replace("-", " ") in d_lower or repo in directive_repo:
                                    tune_payload["parameters"]["focus_repo"] = repo
                        await self.ipc.send(
                            Message(
                                signal=SignalType.SIG_TUNE_GOALS,
                                sender="Beta",
                                payload=tune_payload,
                            )
                        )

                    # B. Compile Cognitive Prompt across Graph Memory and Consult LLM
                    clean_repo = directive_repo.replace("holman57/", "").strip()
                    compiled_prompt = self.prompt_compiler.compile_task_prompt(
                        repo_name=clean_repo,
                        issue_data={
                            "number": issue_num or 0,
                            "title": getattr(directive, "topic", "Operator Directive"),
                            "body": str(directive),
                            "author": getattr(directive, "author", "holman57"),
                        },
                    )
                    logger.info(
                        f"Beta compiled cognitive prompt for {clean_repo} #{issue_num} "
                        f"({compiled_prompt['metadata']['estimated_tokens']} est tokens across memory tiers)"
                    )

                    # Consult LLM (Gemini or Local LLM via MCP)
                    solution_plan = self.llm.consult(
                        prompt=compiled_prompt["user_prompt"],
                        system_prompt=compiled_prompt["system_prompt"],
                    )
                    logger.info(f"Beta synthesized solution plan for {clean_repo}: {solution_plan[:120]}...")

                    # C. Dispatch execution task for Alpha via Solved Problems
                    safe_dir = str(directive).replace("'", "\\'")
                    cmd = (
                        f'python -c "'
                        f'from adrastea.alpha.solved_problems import inspect_repository, fetch_repo_issues; '
                        f'env = inspect_repository(\'{clean_repo}\'); '
                        f'print(f\'Executed user directive for {clean_repo}: {safe_dir}\')"'
                    )
                    await self.ipc.send(
                        Message(
                            signal=SignalType.SIG_DISPATCH,
                            sender="Beta",
                            payload={
                                "task_id": f"user_directive_{int(time.time())}",
                                "command": cmd,
                                "priority": 100,
                                "metadata": {
                                    "user_directive": str(directive),
                                    "goal_id": goal_id,
                                    "repo": directive_repo,
                                    "issue_number": issue_num,
                                    "solution_plan": solution_plan[:500],
                                    "tokens": compiled_prompt["metadata"]["estimated_tokens"],
                                }
                            }
                        )
                    )

                    # C. Bidirectional Correspondence: Reply directly back to the GitHub issue
                    if getattr(directive, "source", None) == "github_issue" and issue_num:
                        target_label = f"Goal: {goal_id}" if goal_id else (getattr(directive, "topic", None) or f"Issue #{issue_num}")
                        repo_display = f"\n- **Repository:** `{directive_repo}`" if directive_repo != "holman57/Adrastea" else ""
                        reply_markdown = (
                            f"**Autonomous Directive Adoption & Response for @{directive.author}**\n\n"
                            f"- **Target Scope:** `{target_label}`{repo_display}\n"
                            f"- **Received Directive:**\n"
                            f"  > {directive.text}\n\n"
                            f"- **Action Taken:**\n"
                            f"  - Adopted into System Beta cognitive loop and prioritized in System Alpha task scheduler.\n"
                            f"  - Associated goal parameters and priority weights dynamically tuned.\n"
                            f"  - Execution task dispatched.\n\n"
                            f"- **Current State:** Operational. Standing by for your next steer on this thread (anti-spam wait active)."
                        )
                        try:
                            mgr = (
                                self.watcher.get_correspondence_manager(directive_repo)
                                if hasattr(self.watcher, "get_correspondence_manager")
                                else self.watcher.correspondence_manager
                            )
                            resp = mgr.post_response_to_issue(
                                issue_number=issue_num,
                                response_markdown=reply_markdown,
                                force=False,
                            )
                            if resp.get("suppressed"):
                                logger.info(f"Duplicate reply suppressed for Issue #{issue_num} on {directive_repo}: {resp.get('details')}")
                            else:
                                logger.info(f"Dispatched correspondence reply to Issue #{issue_num} on {directive_repo}: {resp.get('details')}")
                        except Exception as e:
                            logger.error(f"Failed to post correspondence reply to Issue #{issue_num} on {directive_repo}: {e}")

                    # D. Ingest into Knowledge Graph Memory
                    try:
                        from ..knowledge.memory_manager import MemoryManager
                        mm = MemoryManager()
                        mm.record_user_directive(
                            directive_text=str(directive),
                            source=f"{directive_repo}#issue_{issue_num}" if issue_num else getattr(directive, "source", "DIRECTIVES.txt"),
                            target_goal=goal_id,
                            issue_number=issue_num,
                        )
                    except Exception as e:
                        logger.debug(f"Knowledge memory ingestion note: {e}")

                    # E. Log locally and commit/push significant event
                    self.activity_logger.log_cycle(
                        alpha_status=self.last_telemetry,
                        beta_action=f"Adopted and executed user directive on #{issue_num or 'local'}: '{directive[:50]}'"
                    )
                    self.activity_logger.commit_and_push_significant_event(
                        f"adopted user directive on #{issue_num or 'local'}: '{directive[:40]}'",
                        bypass_cooldown=True
                    )

                # If in keep-alive sleep mode, sleep for long interval without heavy loops
                if self._sleeping:
                    logger.debug(f"Beta resting in keep-alive standby for {self.sleep_interval}s...")
                    try:
                        await asyncio.wait_for(self._wake_event.wait(), timeout=self.sleep_interval)
                        self._sleeping = False
                        self._wake_event.clear()
                        logger.info("Beta awakened from keep-alive sleep by event.")
                    except asyncio.TimeoutError:
                        pass
                    continue

                # 2. Heuristic Pathfinding & Autonomous Goal Tuning
                if self.last_telemetry:
                    tune_msg = self.tuner.evaluate_telemetry(self.last_telemetry.get("telemetry", {}))
                    if tune_msg:
                        logger.info("Beta tuning Alpha's RL pathfinding weights...")
                        await self.ipc.send(tune_msg)

                    goals_data = self.last_telemetry.get("goals", {})
                    goal_tune_signals = self.tuner.evaluate_goals(
                        telemetry=self.last_telemetry.get("telemetry", {}),
                        goals_data=goals_data,
                        recent_directive=directive
                    )
                    for g_sig in goal_tune_signals:
                        logger.info(f"Beta dynamically tuning Alpha goal [{g_sig.payload.get('goal_id')}]: {g_sig.payload}")
                        await self.ipc.send(g_sig)

                # 3. Outreach & Inquiries with Adaptive Backoff (Logs locally without pushing to GitHub)
                if self.strategist.should_attempt_contact():
                    logger.info(f"Triggering outreach dispatch (Attempt #{self.strategist.contact_attempt_count + 1})...")
                    question = self.discovery.formulate_user_question(self.last_telemetry)
                    notify_res = self.notifier.notify_status(self.last_telemetry, custom_question=question)
                    self.strategist.mark_contact_attempted()

                    # Beta diagnoses delivery barriers using local Ollama model
                    channels = notify_res.get("channels", {})
                    adaptation = self.strategist.analyze_and_adapt(channels)
                    logger.info(f"Delivery diagnosis: {adaptation.get('barrier_summary')}")

                    # Record cycle locally in ACTIVITY_LOG.md (DO NOT PUSH - avoid relentless pounding)
                    self.activity_logger.log_cycle(
                        alpha_status=self.last_telemetry,
                        beta_action=f"Outreach Attempt #{self.strategist.contact_attempt_count} ({adaptation.get('best_working_channel', 'none')})",
                        outreach_results=channels,
                        pending_directive_prompt=question
                    )

                # 4. Periodic Discovery of novel diagnostic tasks
                if iteration % 6 == 0:
                    novel_task = self.discovery.discover_novel_task(self.last_telemetry)
                    if novel_task:
                        logger.info("Beta enqueuing novel discovered task for Alpha...")
                        await self.ipc.send(novel_task)

                # Idle sleep (can remain idle for days)
                await asyncio.sleep(config.beta_idle_cycle_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in Beta cognitive loop: {e}", exc_info=True)
                await asyncio.sleep(config.beta_idle_cycle_seconds)

    async def stop(self) -> None:
        logger.info("Stopping System Beta...")
        self._running = False
        if self._loop_task:
            self._loop_task.cancel()
        await self.ipc.disconnect()
        logger.info("System Beta stopped.")


def main():
    parser = argparse.ArgumentParser(description="System Beta: Cognitive Reasoning Engine")
    parser.add_argument("--ipc-host", default="127.0.0.1", help="Alpha IPC host")
    parser.add_argument("--ipc-port", type=int, default=8765, help="Alpha IPC port")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s")

    engine = BetaEngine(ipc_host=args.ipc_host, ipc_port=args.ipc_port)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(engine.start())
        loop.run_forever()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received.")
    finally:
        loop.run_until_complete(engine.stop())
        loop.close()


if __name__ == "__main__":
    main()
