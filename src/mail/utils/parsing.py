import importlib
from typing import Any


def read_python_string(string: str) -> Any:
    """
    Read a python variable from a python file
    The string should be in the format of "module:variable"
    """
    module_str, variable = string.split(":")
    module = importlib.import_module(module_str)
    return getattr(module, variable)