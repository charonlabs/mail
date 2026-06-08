# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Charon Labs

"""Reporter agent for the Data Analysis swarm."""

from mail.examples.data_analysis.reporter.agent import LiteLLMReporterFunction
from mail.examples.data_analysis.reporter.actions import format_report
from mail.examples.data_analysis.reporter.prompts import SYSPROMPT

__all__ = ["LiteLLMReporterFunction", "format_report", "SYSPROMPT"]
