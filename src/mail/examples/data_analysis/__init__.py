# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Charon Labs

"""Data Analysis example swarm.

This swarm demonstrates data processing pipelines with statistical analysis
and report generation. It uses a mix of real calculations and dummy data generation.

Agents:
    - analyst: Entry point that coordinates analysis workflows
    - processor: Handles data ingestion, cleaning, and transformation
    - statistics: Performs statistical calculations (real implementations)
    - reporter: Generates formatted reports and summaries
"""

from mail.examples.data_analysis.analyst.agent import LiteLLMAnalystFunction
from mail.examples.data_analysis.processor.agent import LiteLLMProcessorFunction
from mail.examples.data_analysis.processor.actions import (
    generate_sample_data,
    parse_csv,
)
from mail.examples.data_analysis.statistics.agent import LiteLLMStatisticsFunction
from mail.examples.data_analysis.statistics.actions import (
    calculate_statistics,
    run_correlation,
)
from mail.examples.data_analysis.reporter.agent import LiteLLMReporterFunction
from mail.examples.data_analysis.reporter.actions import format_report

__all__ = [
    "LiteLLMAnalystFunction",
    "LiteLLMProcessorFunction",
    "LiteLLMStatisticsFunction",
    "LiteLLMReporterFunction",
    "generate_sample_data",
    "parse_csv",
    "calculate_statistics",
    "run_correlation",
    "format_report",
]
