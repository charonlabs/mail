# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import importlib
import json
from typing import Any

import httpx

from mail.core import parse_agent_address

PYTHON_STRING_PREFIX = "python::"
URL_STRING_PREFIX = "url::"


def read_python_string(string: str) -> Any:
    """
    Resolve an import string to a Python object.

    Accepts strings in the format ``module:variable`` or with the explicit
    ``python::`` prefix used in swarm configuration files, e.g.
    ``python::package.module:object``.
    """

    if string.startswith(PYTHON_STRING_PREFIX):
        string = string[len(PYTHON_STRING_PREFIX) :]

    try:
        module_str, attribute_path = string.split(":", 1)
    except ValueError as err:  # pragma: no cover - defensive guard
        raise ValueError(
            f"Invalid python reference '{string}'. Expected 'module:object' format."
        ) from err

    module = importlib.import_module(module_str)
    obj: Any = module
    for attr in attribute_path.split("."):
        obj = getattr(obj, attr)

    return obj


def resolve_prefixed_string_references(value: Any) -> Any:
    """
    Recursively resolve strings prefixed with ``python::`` or ``url::`` to Python objects or strings, respectively.
    """

    if isinstance(value, dict):
        return {
            key: resolve_prefixed_string_references(item) for key, item in value.items()
        }
    if isinstance(value, list):
        return [resolve_prefixed_string_references(item) for item in value]
    if isinstance(value, str):
        if value.startswith(PYTHON_STRING_PREFIX):
            return read_python_string(value)
        if value.startswith(URL_STRING_PREFIX):
            return read_url_string(value)
        return value

    return value


def read_url_string(string: str, raise_on_error: bool = False) -> str:
    """
    Resolve a URL to a string.

    Accepts strings in the format ``url::`` prefix used in swarm configuration files, e.g.
    ``url::https://example.com``.
    """

    if string.startswith(URL_STRING_PREFIX):
        string = string[len(URL_STRING_PREFIX) :]

    try:
        response = httpx.get(string)
        return json.dumps(response.json())
    except Exception as e:
        if raise_on_error:
            raise RuntimeError(f"error reading URL string: '{str(e)}'")
        return string


def target_address_is_interswarm(address: str) -> bool:
    """
    Check if a target address is an interswarm address.
    """

    return parse_agent_address(address)[1] is not None
