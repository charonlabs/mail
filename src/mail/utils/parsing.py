# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import importlib
from typing import Any

from mail.core import parse_agent_address


PYTHON_STRING_PREFIX = "python::"


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


def resolve_python_references(value: Any) -> Any:
	"""Recursively resolve strings prefixed with ``python::`` to Python objects."""

	if isinstance(value, dict):
		return {key: resolve_python_references(item) for key, item in value.items()}
	if isinstance(value, list):
		return [resolve_python_references(item) for item in value]
	if isinstance(value, str) and value.startswith(PYTHON_STRING_PREFIX):
		return read_python_string(value)
	return value


def target_address_is_interswarm(address: str) -> bool:
	"""
	Check if a target address is an interswarm address.
	"""
	return parse_agent_address(address)[1] is not None
