from .factories.action import ActionFunction
from .factories.base import AgentToolCall


async def execute_action_tool(
    call: AgentToolCall, actions: dict[str, ActionFunction]
) -> dict[str, str]:
    action = actions[call.tool_name]
    content = await action(call.tool_args)
    return call.create_response_msg(content)
