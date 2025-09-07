import importlib
from typing import Any, Literal


def read_python_string(string: str) -> Any:
    """
    Read a python variable from a python file
    The string should be in the format of "module:variable"
    """
    module_str, variable = string.split(":")
    module = importlib.import_module(module_str)
    return getattr(module, variable)


def create_tools_from_actions(
    actions: list[dict[str, Any]],
    style: Literal["completions", "responses"] = "completions",
) -> list[dict[str, Any]]:
    """Create OpenAI function tools from action specs.

    Uses the action's declared name/description/parameters instead of attempting
    to infer schema from the Python function (which may be opaque/coroutine).
    """
    tools: list[dict[str, Any]] = []
    for action in actions:
        name = action.get("name", "").strip()
        if not name:
            # Skip unnamed actions to avoid invalid tool specs
            continue
        description = action.get("description", "")
        parameters = action.get("parameters", {"type": "object", "properties": {}})

        parameters["additionalProperties"] = False
        parameters["required"] = [
            property for property in parameters["properties"].keys()
        ]

        if style == "completions":
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": description,
                        "parameters": parameters,
                        "strict": True,
                    },
                }
            )
        elif style == "responses":
            tools.append(
                {
                    "type": "function",
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                }
            )
        else:
            raise ValueError(f"invalid style: {style}")

    return tools
