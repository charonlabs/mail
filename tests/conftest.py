# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import os
from collections.abc import Callable
from typing import Any, Literal

import pytest


class FakeSwarmRegistry:
	"""
	Fake `SwarmRegistry` for testing.
	"""

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
		"""
		Get a swarm endpoint by name.
		"""
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
		"""
		Register a swarm endpoint.
		"""
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
		"""
		Get all swarm endpoints.
		"""
		return self._endpoints.copy()


def make_stub_agent(
	# REQUIRED
	# top-level params
	comm_targets: list[str],
	tools: list[dict[str, Any]],
	# instance params
	user_token: str = "secret-token",
	# internal params
	llm: str = "openai/gpt-5-mini",
	system: str = "mail.examples.analyst_dummy.prompts:SYSPROMPT",
	# OPTIONAL
	# top-level params
	name: str = "base_agent",
	enable_entrypoint: bool = False,
	enable_interswarm: bool = False,
	can_complete_tasks: bool = False,
	tool_format: Literal["completions", "responses"] = "responses",
	# instance params
	# ...
	# internal params
	reasoning_effort: Literal["minimal", "low", "medium", "high"] | None = None,
	thinking_budget: int | None = None,
	max_tokens: int | None = None,
	memory: bool = True,
	use_proxy: bool = True,
	_debug_include_mail_tools: bool = True,
) -> Callable:
	"""
	Make a stub agent for testing.
	"""
	if len(tools) == 0:
		tools = [{"name": "task_complete", "args": {"finish_message": "Task finished"}}]

	async def agent(history: list[dict[str, Any]], tool_choice: str):  # noqa: ARG001
		from mail.factories.base import AgentToolCall

		call = AgentToolCall(
			tool_name=tools[0]["name"],
			tool_args=tools[0]["args"],
			tool_call_id="call-1",
			completion={"role": "assistant", "content": "ok"},
		)
		return None, [call]

	return agent


@pytest.fixture(autouse=True)
def set_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
	"""
	Set the authentication environment variables.
	"""
	# Prevent accidental external calls by ensuring endpoints are set to dummy
	monkeypatch.setenv("AUTH_ENDPOINT", "http://test-auth.local/login")
	monkeypatch.setenv("TOKEN_INFO_ENDPOINT", "http://test-auth.local/token-info")
	monkeypatch.setenv("SWARM_NAME", "example")
	monkeypatch.setenv("BASE_URL", "http://localhost:8000")


@pytest.fixture()
def patched_server(monkeypatch: pytest.MonkeyPatch):
	"""
	Patch server dependencies to avoid network and heavy LLM calls.

	This fixture patches the `SwarmRegistry`, `MAILSwarmTemplate.from_swarm_json_file`, and `MAILSwarm.submit_message` to avoid network and heavy LLM calls.
	"""
	# Reset global server state to avoid cross-test interference
	import mail.server as server
	from mail.api import MAILAgentTemplate, MAILSwarmTemplate

	server.user_mail_instances.clear()
	server.user_mail_tasks.clear()
	server.swarm_mail_instances.clear()
	server.swarm_mail_tasks.clear()

	# Fake registry prevents network
	monkeypatch.setattr("mail.net.registry.SwarmRegistry", FakeSwarmRegistry)

	stub_swarm = MAILSwarmTemplate(
		name=os.getenv("SWARM_NAME", "example"),
		agents=[
			MAILAgentTemplate(
				name="supervisor",
				# Use importable path for read_python_string
				factory="tests.conftest:make_stub_agent",
				comm_targets=["analyst"],
				actions=[],
				agent_params={},
				can_complete_tasks=True,
				enable_entrypoint=True,
				enable_interswarm=False,
			),
			MAILAgentTemplate(
				name="analyst",
				factory="tests.conftest:make_stub_agent",
				comm_targets=["supervisor"],
				actions=[],
				agent_params={},
			),
		],
		actions=[],
		entrypoint="supervisor",
		enable_interswarm=True,
	)

	# Ensure the server uses our stub swarm template instead of reading swarms.json
	monkeypatch.setattr(
		"mail.MAILSwarmTemplate.from_swarm_json_file",
		lambda path, name: stub_swarm,  # noqa: ARG005
	)

	# Make MAILSwarm.submit_message return only the response object to match server usage
	async def _compat_submit_message(
		self, message, timeout: float = 3600.0, show_events: bool = False
	):  # noqa: ANN001, D401, ARG002, FBT001, FBT002
		# Bypass events tuple to keep server logic simple in tests
		return await self._runtime.submit_and_wait(message, timeout)  # type: ignore[attr-defined]

	monkeypatch.setattr(
		"mail.MAILSwarm.submit_message", _compat_submit_message, raising=True
	)

	# Stub auth calls to avoid aiohttp
	monkeypatch.setattr(
		"mail.utils.auth.login", lambda api_key: _async_return("fake-jwt")
	)
	monkeypatch.setattr(
		"mail.utils.auth.get_token_info",
		lambda token: _async_return({"role": "user", "id": "u-123"}),
	)

	yield


def _async_return(value):
	async def _inner():
		return value

	return _inner()
