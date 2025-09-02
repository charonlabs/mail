from .factories.action import ActionFunction, ActionOverrideFunction
from .factories.base import AgentToolCall


async def execute_action_tool(
    call: AgentToolCall,
    actions: dict[str, ActionFunction],
    _action_override: ActionOverrideFunction | None = None,
) -> dict[str, str]:
    if not _action_override:
        action = actions[call.tool_name]
        content = await action(call.tool_args)
        return call.create_response_msg(content)
    response = await _action_override(call.tool_args)
    if isinstance(response, str):
        return call.create_response_msg(response)
    return response
