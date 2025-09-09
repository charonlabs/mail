import asyncio

from mail.executor import execute_action_tool
from mail.factories.base import AgentToolCall


def _call(name: str, args: dict) -> AgentToolCall:
    return AgentToolCall(
        tool_name=name,
        tool_args=args,
        tool_call_id="t1",
        completion={"role": "assistant", "content": "ok"},
    )


async def _action_echo(args: dict) -> str:  # noqa: ANN001
    return f"echo:{args.get('x')}"


async def _override_upper(args: dict):  # noqa: ANN001
    return f"OVERRIDE:{str(args.get('x')).upper()}"


def test_execute_action_tool_normal_and_override():
    async def run():
        # Normal path: resolves through actions mapping and wraps as tool response
        res1 = await execute_action_tool(
            _call("echo", {"x": 3}), {"echo": _action_echo}
        )
        assert res1["role"] == "tool" and "echo:3" in res1["content"]

        # Override returns a string or dict directly
        res2 = await execute_action_tool(
            _call("echo", {"x": "hi"}),
            {"echo": _action_echo},
            _action_override=_override_upper,
        )
        assert res2["content"].startswith("OVERRIDE:")

    asyncio.run(run())
