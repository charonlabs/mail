# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import importlib
from typing import Any

from mail.core import parse_agent_address


def read_python_string(string: str) -> Any:
	"""
	Read a python variable from a python file
	The string should be in the format of "module:variable"
	"""
	module_str, variable = string.split(":")
	module = importlib.import_module(module_str)
	return getattr(module, variable)


def target_address_is_interswarm(address: str) -> bool:
	"""
	Check if a target address is an interswarm address.
	"""
	return parse_agent_address(address)[1] is not None
