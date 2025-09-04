import importlib
from typing import Any

from litellm.utils import function_to_dict


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
        # Get the actual function object from the module path
        function_obj = read_python_string(action["function"])
        # Convert the function to a tool dictionary
        tools.append(function_to_dict(function_obj))
    return tools
