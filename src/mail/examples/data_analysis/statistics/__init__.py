# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Charon Labs

"""Statistics agent for the Data Analysis swarm."""

from mail.examples.data_analysis.statistics.agent import LiteLLMStatisticsFunction
from mail.examples.data_analysis.statistics.actions import (
    calculate_statistics,
    run_correlation,
)
from mail.examples.data_analysis.statistics.prompts import SYSPROMPT

__all__ = [
    "LiteLLMStatisticsFunction",
    "calculate_statistics",
    "run_correlation",
    "SYSPROMPT",
]
