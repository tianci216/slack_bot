"""
Multi-bot process manager.

Reads bot configs from bots/*.json and spawns main.py for each.
Monitors child processes and restarts any that crash.
"""

import os
import sys
import json
import time
import signal
import logging
import subprocess
from pathlib import Path

BOT_DIR = Path(__file__).parent
BOTS_DIR = BOT_DIR / "bots"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - run_all - %(levelname)s - %(message)s'
)
logger = logging.getLogger("run_all")

processes: dict[str, subprocess.Popen] = {}
shutting_down = False


def start_bot(config_path: Path) -> subprocess.Popen:
    """Start a bot subprocess."""
    config = json.loads(config_path.read_text())
    name = config["name"]
    rel_path = config_path.relative_to(BOT_DIR)

    proc = subprocess.Popen(
        [sys.executable, str(BOT_DIR / "main.py"), "--config", str(rel_path)],
        cwd=str(BOT_DIR),
    )
    logger.info(f"Started bot '{name}' (PID {proc.pid})")
    return proc


def shutdown(signum, frame):
    """Gracefully stop all bots."""
    global shutting_down
    shutting_down = True
    logger.info("Shutting down all bots...")
    for name, proc in processes.items():
        logger.info(f"Stopping bot '{name}' (PID {proc.pid})")
        proc.terminate()
    for name, proc in processes.items():
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            logger.warning(f"Bot '{name}' did not stop gracefully, killing")
            proc.kill()
    sys.exit(0)


def main():
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    config_files = sorted(BOTS_DIR.glob("*.json"))
    if not config_files:
        logger.error(f"No bot configs found in {BOTS_DIR}")
        sys.exit(1)

    logger.info(f"Found {len(config_files)} bot config(s)")

    for config_path in config_files:
        config = json.loads(config_path.read_text())
        name = config["name"]
        processes[name] = start_bot(config_path)

    logger.info("All bots started. Monitoring processes...")

    # Monitor and restart crashed bots
    while not shutting_down:
        for name, proc in list(processes.items()):
            retcode = proc.poll()
            if retcode is not None:
                logger.warning(f"Bot '{name}' exited with code {retcode}. Restarting in 5s...")
                time.sleep(5)
                if not shutting_down:
                    config_path = BOTS_DIR / f"{name}.json"
                    processes[name] = start_bot(config_path)
        time.sleep(3)


if __name__ == "__main__":
    main()
