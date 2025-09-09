import os
from typing import Any, Callable

import pytest


class FakeSwarmRegistry:
    def __init__(
        self, local_swarm_name: str, base_url: str, persistence_file: str
    ) -> None:  # noqa: ARG002
        self.local_swarm_name = local_swarm_name
        self.base_url = base_url
        self.persistence_file = persistence_file
        # Shape mirrors real SwarmRegistry.get_all_endpoints entries
        self._endpoints: dict[str, dict[str, Any]] = {
            local_swarm_name: {
                "swarm_name": local_swarm_name,
                "base_url": base_url,
                "is_active": True,
                "last_seen": None,
                "metadata": None,
            }
        }

    async def start_health_checks(self) -> None:  # no network
        return None

    async def stop_health_checks(self) -> None:  # no network
        return None

    def cleanup_volatile_endpoints(self) -> None:
        return None

    def get_swarm_endpoint(self, name: str) -> dict[str, Any] | None:
        # Accept either key by swarm name or lookup by swarm_name field
        if name in self._endpoints:
            return self._endpoints.get(name)
        for key, ep in self._endpoints.items():
            if ep.get("swarm_name") == name:
                return ep
        return None

    # Helpers used by some server endpoints
    def register_swarm(
        self,
        swarm_name: str,
        base_url: str,
        auth_token: str | None = None,  # noqa: ARG002
        metadata: dict[str, Any] | None = None,
        volatile: bool = True,  # noqa: FBT001, FBT002
    ) -> None:
        if swarm_name == self.local_swarm_name:
            return
        self._endpoints[swarm_name] = {
            "swarm_name": swarm_name,
            "base_url": base_url,
            "is_active": True,
            "last_seen": None,
            "metadata": metadata,
            "volatile": volatile,
        }

    def get_all_endpoints(self) -> dict[str, dict[str, Any]]:
        return self._endpoints.copy()


def make_stub_agent(
    tool_name: str = "task_complete", tool_args: dict[str, Any] | None = None
) -> Callable:
    if tool_args is None:
        tool_args = {"finish_message": "Task finished"}

    async def agent(history: list[dict[str, Any]], tool_choice: str):  # noqa: ARG001
        from mail.factories.base import AgentToolCall

        call = AgentToolCall(
            tool_name=tool_name,
            tool_args=tool_args,
            tool_call_id="call-1",
            completion={"role": "assistant", "content": "ok"},
        )
        return None, [call]

    return agent


@pytest.fixture(autouse=True)
def set_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Prevent accidental external calls by ensuring endpoints are set to dummy
    monkeypatch.setenv("AUTH_ENDPOINT", "http://test-auth.local/login")
    monkeypatch.setenv("TOKEN_INFO_ENDPOINT", "http://test-auth.local/token-info")
    monkeypatch.setenv("SWARM_NAME", "example")
    monkeypatch.setenv("BASE_URL", "http://localhost:8000")


@pytest.fixture()
def patched_server(monkeypatch: pytest.MonkeyPatch):
    """Patch server dependencies to avoid network and heavy LLM calls.

    - Replace SwarmRegistry with a fake no-op implementation
    - Stub build_swarm_from_name to a minimal swarm with one agent 'supervisor'
    - Stub auth.login and auth.get_token_info to return deterministic values
    - Force default entrypoint to 'supervisor'
    """
    from mail.swarms.swarm import Agent, Swarm

    # Reset global server state to avoid cross-test interference
    import mail.server as server

    server.user_mail_instances.clear()
    server.user_mail_tasks.clear()
    server.swarm_mail_instances.clear()
    server.swarm_mail_tasks.clear()

    # Fake registry prevents network
    monkeypatch.setattr("mail.server.SwarmRegistry", FakeSwarmRegistry)

    # Build a minimal swarm with a stub supervisor agent
    def _factory(**kwargs: Any):  # noqa: ANN001, ANN003, ARG001
        return make_stub_agent()

    stub_swarm = Swarm(
        name=os.getenv("SWARM_NAME", "example"),
        agents=[
            Agent(
                name="supervisor",
                factory=_factory,  # type: ignore[arg-type]
                llm="mock",
                system="You are a helpful supervisor.",
                comm_targets=["analyst"],
                agent_params={"actions": []},
                tools=[],
            )
        ],
        default_entrypoint="supervisor",
    )

    monkeypatch.setattr("mail.server.build_swarm_from_name", lambda name: stub_swarm)  # noqa: ARG005

    # Stub auth calls to avoid aiohttp
    monkeypatch.setattr("mail.server.login", lambda api_key: _async_return("fake-jwt"))
    monkeypatch.setattr(
        "mail.server.get_token_info",
        lambda token: _async_return({"role": "user", "id": "u-123"}),
    )

    yield


def _async_return(value):
    async def _inner():
        return value

    return _inner()
