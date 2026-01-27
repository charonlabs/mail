#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Ryan Heaton

"""
Development script to run MAIL server and UI together.

Starts:
- MAIL server with a 2-agent swarm (Supervisor + Researcher) - logs to file
- Next.js UI dev server - logs to terminal

Usage:
    python scripts/run_ui_dev.py
    # or
    uv run scripts/run_ui_dev.py
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
UI_DIR = PROJECT_ROOT / "ui"
LOGS_DIR = PROJECT_ROOT / "scripts" / "output"


def create_swarm_json() -> Path:
    """Create a temporary swarm JSON file with 2 Claude agents."""
    swarm_config = {
        "name": "UIDevSwarm",
        "version": "1.0.0",
        "description": "Development swarm for UI testing",
        "agents": [
            {
                "name": "Supervisor",
                "factory": "mail.factories.supervisor:supervisor_factory",
                "comm_targets": ["Researcher"],
                "actions": [],
                "agent_params": {
                    "llm": "anthropic/claude-haiku-4-5-20251001",
                    "system": """You are a supervisor agent. When you receive a task from the user,
delegate it to the Researcher agent by sending them a request.

Once you receive the Researcher's response, use task_complete to finish the task and provide the answer to the user.

Steps:
1. Send a request to Researcher with the user's question
2. Wait for their response
3. Call task_complete with the final answer - this is REQUIRED to end the task""",
                    "use_proxy": False,
                    "reasoning_effort": "low",
                    "tool_format": "completions",
                    "stream_tokens": True,
                },
                "enable_entrypoint": True,
                "enable_interswarm": False,
                "can_complete_tasks": True,
            },
            {
                "name": "Researcher",
                "factory": "mail.factories.base:base_agent_factory",
                "comm_targets": ["Supervisor"],
                "actions": [],
                "agent_params": {
                    "llm": "anthropic/claude-haiku-4-5-20251001",
                    "system": """You are a research assistant. When you receive a request from the Supervisor,
provide a helpful, detailed response based on your knowledge.

Keep responses concise but informative. Always respond to the Supervisor when asked.""",
                    "use_proxy": False,
                    "_debug_include_mail_tools": True,
                    "reasoning_effort": "low",
                    "tool_format": "completions",
                    "stream_tokens": True,
                },
                "enable_entrypoint": False,
                "enable_interswarm": False,
                "can_complete_tasks": False,
            },
        ],
        "actions": [],
        "entrypoint": "Supervisor",
        "enable_interswarm": False,
        "breakpoint_tools": [],
    }

    # Create swarm JSON file in output dir
    # NOTE: The swarms.json format requires a LIST of swarms at the top level
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    swarm_file = LOGS_DIR / "ui_dev_swarm.json"

    with open(swarm_file, "w") as f:
        json.dump([swarm_config], f, indent=2)

    print(f"Created swarm config: {swarm_file}")
    return swarm_file


def create_mail_toml(swarm_file: Path) -> Path:
    """Create a temporary mail.toml config file."""
    config = f"""
[server]
port = 8000
host = "0.0.0.0"
reload = false
debug = true

[server.swarm]
name = "UIDevSwarm"
source = "{swarm_file}"
registry_file = "registries/ui-dev.json"
description = "Development swarm for UI testing"
keywords = ["dev", "ui", "test"]
public = false

[server.settings]
task_message_limit = 30
"""

    config_file = LOGS_DIR / "mail.toml"
    with open(config_file, "w") as f:
        f.write(config)

    print(f"Created mail config: {config_file}")
    return config_file


def main():
    print("=" * 60)
    print("MAIL UI Development Server")
    print("=" * 60)
    print()

    # Create configs
    swarm_file = create_swarm_json()
    config_file = create_mail_toml(swarm_file)

    # Set up log file for MAIL server
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    mail_log_file = LOGS_DIR / f"mail_server_{timestamp}.log"

    print(f"\nMAIL server logs: {mail_log_file}")
    print(f"UI server logs: (terminal)")
    print()
    print("-" * 60)

    # Environment for MAIL server
    mail_env = os.environ.copy()
    mail_env["MAIL_CONFIG_PATH"] = str(config_file)

    # Create registry directory if it doesn't exist
    registry_dir = PROJECT_ROOT / "registries"
    registry_dir.mkdir(exist_ok=True)

    processes = []
    log_file = None

    try:
        # Start MAIL server with logs to file
        print("Starting MAIL server on http://localhost:8000 ...")
        log_file = open(mail_log_file, "w")
        mail_proc = subprocess.Popen(
            [
                "uv", "run", "uvicorn",
                "mail.server:app",
                "--host", "0.0.0.0",
                "--port", "8000",
            ],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=mail_env,
            cwd=PROJECT_ROOT,
        )
        processes.append(("MAIL server", mail_proc))

        # Give MAIL server a moment to start
        time.sleep(2)

        # Check if MAIL server started successfully
        if mail_proc.poll() is not None:
            print(f"\n❌ MAIL server failed to start! Check logs: {mail_log_file}")
            with open(mail_log_file, "r") as f:
                print(f.read()[-2000:])  # Last 2000 chars
            sys.exit(1)

        print("✓ MAIL server started")

        # Start UI dev server with logs to terminal
        print("\nStarting UI dev server on http://localhost:3000 ...")
        print("-" * 60)

        ui_proc = subprocess.Popen(
            ["pnpm", "dev"],
            stdout=sys.stdout,
            stderr=sys.stderr,
            cwd=UI_DIR,
        )
        processes.append(("UI server", ui_proc))

        # Wait for UI process (it's the one showing in terminal)
        ui_proc.wait()

    except KeyboardInterrupt:
        print("\n\nShutting down...")
    finally:
        # Clean up all processes
        for name, proc in processes:
            if proc.poll() is None:
                print(f"Stopping {name}...")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

        # Close log file
        if log_file:
            log_file.close()

        print("\n✓ All servers stopped")
        print(f"MAIL server logs saved to: {mail_log_file}")


if __name__ == "__main__":
    main()
