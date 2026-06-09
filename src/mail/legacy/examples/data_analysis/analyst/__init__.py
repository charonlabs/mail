# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Charon Labs

"""Analyst agent for the Data Analysis swarm."""

from mail.legacy.examples.data_analysis.analyst.agent import LiteLLMAnalystFunction
from mail.legacy.examples.data_analysis.analyst.prompts import SYSPROMPT

__all__ = ["LiteLLMAnalystFunction", "SYSPROMPT"]
