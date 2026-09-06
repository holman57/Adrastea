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


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(config.logs_dir / "adrastea.log", encoding="utf-8")
        ]
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


def main():
    parser = argparse.ArgumentParser(description="Adrastea Autonomous Orchestrator")
    parser.add_argument("command", choices=["start", "notify", "test-llm", "status"], default="start", nargs="?")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose debug logging")
    args = parser.parse_args()

    setup_logging(args.verbose)

    if args.command == "start":
        asyncio.run(run_orchestrator())
    elif args.command == "notify":
        cmd_notify()
    elif args.command == "test-llm":
        cmd_test_llm()
    elif args.command == "status":
        print(f"Target Email: {config.target_email}")
        print(f"Target Phone: {config.target_phone}")
        print(f"Ollama URL: {config.ollama_base_url}")
        print(f"IPC: {config.ipc_host}:{config.ipc_port}")


if __name__ == "__main__":
    main()
