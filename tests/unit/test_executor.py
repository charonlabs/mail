# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import asyncio

from mail.core.actions import ActionCore
from mail.core.tools import AgentToolCall


async def _action_echo(args: dict) -> str:  # noqa: ANN001
    return f"echo:{args.get('x')}"


async def _override_upper(call):  # noqa: ANN001
    return f"OVERRIDE:{str(call.tool_args.get('x')).upper()}"


_action_echo_core = ActionCore(
    function=_action_echo,
    name="echo",
    parameters={"x": int},
)
_override_upper_core = ActionCore(
    function=_override_upper,
    name="override_upper",
    parameters={"x": str},
)


def _call(name: str, args: dict) -> AgentToolCall:
    return AgentToolCall(
        tool_name=name,
        tool_args=args,
        tool_call_id="t1",
        completion={"role": "assistant", "content": "ok"},
    )


def test_execute_action_tool_normal_and_override():
    """
    Test that `execute_action_tool` works as expected.
    """

    async def run():
        # Normal path: resolves through actions mapping and wraps as tool response
        res1_status, res1_message = await _action_echo_core.execute(
            _call("echo", {"x": 3}),
            {"echo": _action_echo_core},
        )
        assert res1_status == "success" and "echo:3" in res1_message["content"]

        # Override returns a string or dict directly
        res2_status, res2_message = await _action_echo_core.execute(
            _call("echo", {"x": "hi"}),
            action_override=_override_upper,
        )
        assert res2_status == "success" and res2_message["content"].startswith(
            "OVERRIDE:"
        )

    asyncio.run(run())
