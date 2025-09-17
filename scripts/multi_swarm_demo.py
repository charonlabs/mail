# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import asyncio
import os
import signal
import subprocess

import aiohttp
from aiohttp import web

from mail.utils.logger import init_logger

AUTH_PORT = int(os.getenv("DEMO_AUTH_PORT", "8999"))
AUTH_BASE = f"http://127.0.0.1:{AUTH_PORT}"


async def _auth_check(request: web.Request) -> web.Response:
    """
    Minimal TOKEN_INFO endpoint used by the demo.
    Accepts tokens of form 'role:id' and returns role/id for MAIL auth.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return web.json_response({"error": "no token"}, status=401)
    token = auth.split(" ", 1)[1]
    # Very small, permissive parser for demo purposes
    if ":" in token:
        role, user_id = token.split(":", 1)
    else:
        # Fallback to user role if not structured
        role, user_id = "user", token
    if role not in ("admin", "user", "agent"):
        return web.json_response({"error": "invalid role"}, status=401)
    return web.json_response(
        {
            "role": role,
            "id": user_id,
            "api_key": "demo",
        }
    )


async def _start_auth_stub(app: web.Application) -> web.AppRunner:
    """
    Start the auth stub.
    """
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", AUTH_PORT)
    await site.start()
    return runner


async def _wait_for_health(url: str, timeout_s: float = 20.0) -> None:
    """
    Wait for the health check to return 200.
    """
    deadline = asyncio.get_event_loop().time() + timeout_s
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(url) as r:
                    if r.status == 200:
                        return
            except Exception:
                pass
            if asyncio.get_event_loop().time() > deadline:
                raise TimeoutError(f"Timed out waiting for {url}")
            await asyncio.sleep(0.25)


def _launch_mail_server(
    name: str, base_url: str, registry_file: str, extra_env: dict[str, str]
) -> subprocess.Popen:
    """
    Launch the mail server.
    """
    env = os.environ.copy()
    env.update(
        {
            "SWARM_NAME": name,
            "BASE_URL": base_url,
            "SWARM_REGISTRY_FILE": registry_file,
            # Point MAIL auth to our stub checker
            "TOKEN_INFO_ENDPOINT": f"{AUTH_BASE}/auth/check",
        }
    )
    env.update(extra_env)

    # Run uvicorn directly (no reload) to avoid orphaned child processes
    port = base_url.split(":")[-1]
    args = [
        "python",
        "-m",
        "uvicorn",
        "mail.server:app",
        "--host",
        "127.0.0.1",
        "--port",
        port,
        "--log-level",
        "warning",
    ]
    return subprocess.Popen(
        args,
        cwd=os.getcwd(),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        shell=False,
        preexec_fn=os.setsid if hasattr(os, "setsid") else None,
    )


def _terminate(proc: subprocess.Popen | None, timeout: float = 5.0) -> None:
    """
    Terminate the process.
    """
    if not proc:
        return
    try:
        if proc.poll() is not None:
            return
        # Try graceful shutdown
        if hasattr(os, "getpgid") and proc.pid:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception:
                proc.terminate()
        else:
            proc.terminate()

        try:
            proc.wait(timeout=timeout)
            return
        except Exception:
            pass

        # Force kill if still alive
        if hasattr(os, "getpgid") and proc.pid:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                proc.kill()
        else:
            proc.kill()
        try:
            proc.wait(timeout=2.0)
        except Exception:
            pass
    finally:
        pass


async def main():
    """
    Main function.
    """
    init_logger()

    # Start minimal auth stub used by both swarms
    auth_app = web.Application()
    auth_app.add_routes([web.get("/auth/check", _auth_check)])
    auth_runner = await _start_auth_stub(auth_app)

    swarm_alpha = None
    swarm_beta = None
    try:
        # Provide inter‑swarm auth tokens (parsed by our auth stub)
        common_env = {
            # Alpha will call Beta with this token; Beta will validate role=agent
            "SWARM_AUTH_TOKEN_SWARM_BETA": "agent:swarm-alpha",
            # Beta will call Alpha with this token; Alpha will validate role=agent
            "SWARM_AUTH_TOKEN_SWARM_ALPHA": "agent:swarm-beta",
        }

        swarm_alpha = _launch_mail_server(
            name="swarm-alpha",
            base_url="http://127.0.0.1:8000",
            registry_file="registries/swarm-alpha.json",
            extra_env=common_env,
        )
        swarm_beta = _launch_mail_server(
            name="swarm-beta",
            base_url="http://127.0.0.1:8001",
            registry_file="registries/swarm-beta.json",
            extra_env=common_env,
        )

        print("waiting for swarms to become healthy...")
        await asyncio.gather(
            _wait_for_health("http://127.0.0.1:8000/health"),
            _wait_for_health("http://127.0.0.1:8001/health"),
        )
        print("swarms are healthy. sending message to swarm-alpha...")

        # Send a request to swarm‑alpha that triggers inter‑swarm routing to swarm‑beta
        user_token = "user:demo"
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://127.0.0.1:8000/message",
                headers={"Authorization": f"Bearer {user_token}"},
                json={
                    "message": (
                        "hello, supervisor! please consult `supervisor@swarm-beta` and return "
                        "a concise answer: what impact will AI have on the global economy by 2030? "
                        "once you receive their response, call `task_complete` to share it with me."
                    ),
                    "entrypoint": "supervisor",
                    "show_events": True,
                    "stream": False,
                },
            ) as response:
                body = await response.text()
                print("response from swarm-alpha:")
                print(body)

    finally:
        # Clean up child processes and auth stub
        _terminate(swarm_alpha)
        _terminate(swarm_beta)
        try:
            await auth_runner.cleanup()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
