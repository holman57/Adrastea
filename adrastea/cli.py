import argparse
import asyncio
import json
import logging
import sys
from .config import config
from .alpha.engine import AlphaEngine
from .tasks.builtins import get_default_scheduled_tasks
from .notifications.notifier import Notifier
from .alpha.local_llm import LocalLLMClient
from .beta.llm_consultant import LLMConsultant

from .sanitizer import SensitiveDataFilter, mask_sensitive_value


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    sensitive_filter = SensitiveDataFilter()
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.addFilter(sensitive_filter)

    file_handler = logging.FileHandler(config.logs_dir / "adrastea.log", encoding="utf-8")
    file_handler.addFilter(sensitive_filter)

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        handlers=[console_handler, file_handler]
    )


async def run_orchestrator():
    logger = logging.getLogger("Adrastea.Main")
    logger.info("==================================================")
    logger.info("   LAUNCHING ADRASTEA DUAL-ENGINE SYSTEM")
    logger.info("==================================================")

    alpha = AlphaEngine()

    # Register default scheduled tasks in Alpha
    for task in get_default_scheduled_tasks():
        alpha.scheduler.register(task)

    # Start Alpha (Alpha stabilizes and then automatically spawns Beta)
    await alpha.start()

    try:
        # Run Alpha loop indefinitely
        while True:
            await asyncio.sleep(1)
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("Shutdown signal received.")
    finally:
        await alpha.stop()


def cmd_notify():
    import datetime
    from .beta.delivery_strategist import DeliveryStrategist
    strategist = DeliveryStrategist()
    if not strategist.should_attempt_contact():
        print(json.dumps({
            "timestamp": datetime.datetime.now().isoformat(),
            "suppressed": True,
            "details": "System is waiting on user response. Suppressing repeat notification.",
        }, indent=2))
        return

    notifier = Notifier()
    status = {
        "uptime_seconds": 0,
        "local_llm_online": True,
        "active_tasks": [],
        "telemetry": {"total_executions": 1, "total_successes": 1, "total_failures": 0}
    }
    question = (
        "Adrastea has initialized and verified contact channels.\n"
        "What directives should Adrastea execute next?\n"
        "1. Benchmark local LLM (qwen3-coder:30b)\n"
        "2. Launch continuous system diagnostic loops\n"
        "3. Stand by for interactive tasks"
    )
    result = notifier.notify_status(status, custom_question=question)
    strategist.mark_contact_attempted()
    print(json.dumps(result, indent=2))


def cmd_test_llm():
    print("Testing local Ollama client...")
    client = LocalLLMClient(base_url=config.ollama_base_url, model=config.ollama_model)
    available = client.is_available()
    print(f"Ollama reachable: {available}")
    if available:
        resp = client.generate("Respond with: Ollama operational.")
        print(f"Ollama response: {resp}")

    print("\nTesting Beta LLM Consultant (with fallback)...")
    consultant = LLMConsultant()
    cons_resp = consultant.consult("Say: LLM Consultant operational.")
    print(f"Consultant response: {cons_resp}")


def cmd_goals():
    from .alpha.goals.manager import GoalManager
    gm = GoalManager()
    status = gm.get_goals_status()
    print("=== ADRASTEA AUTONOMOUS GOALS (SYSTEM ALPHA) ===")
    print(f"Total Goals: {status['total_goals']} | Enabled: {status['enabled_goals']}\n")
    for gid, g in status["goals"].items():
        state = "ENABLED" if g["enabled"] else "DISABLED"
        print(f"[{gid}] - {g['name']} ({state})")
        print(f"  Description : {g['description']}")
        print(f"  Weight      : {g['weight']} (Tweakable by Beta)")
        print(f"  Interval    : {g['interval_seconds']}s")
        print(f"  Parameters  : {g['parameters']}")
        print(f"  Metrics     : {g['metrics']}\n")


def cmd_knowledge():
    from .knowledge.memory_manager import MemoryManager
    mm = MemoryManager()
    stats = mm.get_summary()
    print("=== ADRASTEA KNOWLEDGE BASE & GRAPH MEMORY ===")
    print(f"Backend           : {stats.get('backend')}")
    print(f"Database File     : {stats.get('database_path')}")
    print(f"Total Nodes       : {stats.get('total_nodes')}")
    print(f"Total Edges       : {stats.get('total_relationships')}")
    print(f"Memory Tiers      : {stats.get('tiers')}\n")
    print("Sample Graph Nodes:")
    for n in mm.store.query_nodes(limit=8):
        print(f"  - [{n.tier.value}] {n.label} ({n.id}): {n.properties}")


def cmd_issues(sync: bool = False):
    from .notifications.issue_manager import IssueCorrespondenceManager
    mgr = IssueCorrespondenceManager()
    if sync:
        print("Synchronizing and ensuring all goal and question issues on GitHub...")
        res = mgr.ensure_all_issues()
        if res.get("created"):
            print(f"Created issues: {res['created']}")
    else:
        mgr.sync_registry()

    reg = mgr.registry
    print("=== ADRASTEA DECENTRALIZED GITHUB ISSUE THREADS ===")
    print("\n--- Autonomous Goals ---")
    monitored_nums = set()
    for gid, gdata in reg.get("goals", {}).items():
        num = gdata["issue_number"]
        monitored_nums.add(num)
        waiting, reason = mgr.is_waiting_for_user_response(num)
        status_str = "WAITING ON LUKE (@holman57)" if waiting else "SAFE TO RESPOND / ACTIVE"
        print(f"  Issue #{num:02d} | Goal: [{gid}]")
        print(f"    Title  : {gdata['title']}")
        print(f"    Status : {status_str}")
        print(f"    Details: {reason}")
        print(f"    URL    : https://github.com/{mgr.repo}/issues/{num}\n")

    print("--- Architectural Questions ---")
    for qid, qdata in reg.get("questions", {}).items():
        num = qdata["issue_number"]
        monitored_nums.add(num)
        waiting, reason = mgr.is_waiting_for_user_response(num)
        status_str = "WAITING ON LUKE (@holman57)" if waiting else "SAFE TO RESPOND / ACTIVE"
        print(f"  Issue #{num:02d} | Question: [{qid}]")
        print(f"    Title  : {qdata['title']}")
        print(f"    Status : {status_str}")
        print(f"    Details: {reason}")
        print(f"    URL    : https://github.com/{mgr.repo}/issues/{num}\n")

    # Check for any other open issues in the repo
    open_issues = mgr.list_open_issues()
    other_issues = [i for i in open_issues if int(i["number"]) not in monitored_nums]
    if other_issues:
        print("--- Other Monitored Repository Issues ---")
        for oi in other_issues:
            onum = int(oi["number"])
            waiting, reason = mgr.is_waiting_for_user_response(onum)
            status_str = "WAITING ON LUKE (@holman57)" if waiting else "SAFE TO RESPOND / ACTIVE"
            print(f"  Issue #{onum:02d} | User / Direct Directive Thread")
            print(f"    Title  : {oi.get('title', '')}")
            print(f"    Status : {status_str}")
            print(f"    Details: {reason}")
            print(f"    URL    : https://github.com/{mgr.repo}/issues/{onum}\n")


def cmd_directives():
    from .directives import DirectiveWatcher
    watcher = DirectiveWatcher()
    directive = watcher.check_directives(force=True)
    print("=== ADRASTEA DIRECTIVES CHECK ===")
    if directive:
        print("Directive DETECTED:")
        print(f"  Text         : {directive.text}")
        print(f"  Author       : {directive.author}")
        print(f"  Source       : {directive.source}")
        print(f"  Issue Number : {directive.issue_number}")
        print(f"  Target Goal  : {directive.goal_id}")
        print(f"  Topic        : {directive.topic}")
    else:
        print("No new directives found across DIRECTIVES.txt or monitored GitHub issues.")


def main():
    parser = argparse.ArgumentParser(description="Adrastea Autonomous Orchestrator")
    parser.add_argument(
        "command",
        choices=["start", "keepalive", "ping", "wake", "sleep", "notify", "test-llm", "status", "goals", "knowledge", "issues", "directives"],
        default="start",
        nargs="?"
    )
    parser.add_argument("--sync", action="store_true", help="Sync/create all goal and question issues on GitHub")
    parser.add_argument("--sleep-interval", type=float, default=config.keepalive_sleep_seconds, help="Sleep duration in seconds for keep-alive")
    parser.add_argument("--duration", type=float, default=config.keepalive_sleep_seconds, help="Duration in seconds for sleep command")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose debug logging")
    args = parser.parse_args()

    setup_logging(args.verbose)

    if args.command == "start":
        asyncio.run(run_orchestrator())
    elif args.command == "keepalive":
        from .keepalive import run_keepalive_service
        asyncio.run(run_keepalive_service(args.sleep_interval))
    elif args.command == "ping":
        from .keepalive import KeepAliveProcess
        res = asyncio.run(KeepAliveProcess.ping())
        if res:
            print(f"PONG: Adrastea is ALIVE. Roundtrip: {res.get('roundtrip_ms')}ms")
            print(f"State: {'SLEEPING (Keep-Alive)' if res.get('sleeping') else 'ACTIVE'}")
            print(f"Uptime: {res.get('uptime_seconds')}s | Beta Alive: {res.get('beta_alive')}")
        else:
            print("FAILED: Adrastea is not responding.")
            sys.exit(1)
    elif args.command == "wake":
        from .keepalive import KeepAliveProcess
        res = asyncio.run(KeepAliveProcess.remote_wake())
        print(f"Result: {res}")
    elif args.command == "sleep":
        from .keepalive import KeepAliveProcess
        res = asyncio.run(KeepAliveProcess.remote_sleep(duration=args.duration))
        print(f"Result: {res}")
    elif args.command == "notify":
        cmd_notify()
    elif args.command == "test-llm":
        cmd_test_llm()
    elif args.command == "goals":
        cmd_goals()
    elif args.command == "knowledge":
        cmd_knowledge()
    elif args.command == "issues":
        cmd_issues(sync=args.sync)
    elif args.command == "directives":
        cmd_directives()
    elif args.command == "status":
        print(f"Target Email: {mask_sensitive_value(config.target_email)}")
        print(f"Target Phone: {mask_sensitive_value(config.target_phone)}")
        print(f"Ollama URL: {config.ollama_base_url}")
        print(f"IPC: {config.ipc_host}:{config.ipc_port}")
        from .alpha.goals.manager import GoalManager
        from .knowledge.memory_manager import MemoryManager
        gm = GoalManager()
        mm = MemoryManager()
        print(f"Autonomous Goals: {len(gm.goals)} active")
        print(f"Knowledge Graph: {mm.get_summary().get('total_nodes')} nodes, {mm.get_summary().get('total_relationships')} edges")


if __name__ == "__main__":
    main()
