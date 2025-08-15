import importlib
from typing import Any

from langchain_core.utils.function_calling import convert_to_openai_tool


def read_python_string(string: str) -> Any:
    """
    Read a python variable from a python file
    The string should be in the format of "module:variable"
    """
    module_str, variable = string.split(":")
    module = importlib.import_module(module_str)
    return getattr(module, variable)


def create_tools_from_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Create tools from a list of actions.
    """
    tools = []
    for action in actions:
        tools.append(convert_to_openai_tool(action))
    return tools
