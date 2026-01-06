# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Charon Labs

"""Processor agent for the Data Analysis swarm."""

from mail.examples.data_analysis.processor.agent import LiteLLMProcessorFunction
from mail.examples.data_analysis.processor.actions import (
    generate_sample_data,
    parse_csv,
)
from mail.examples.data_analysis.processor.prompts import SYSPROMPT

__all__ = ["LiteLLMProcessorFunction", "generate_sample_data", "parse_csv", "SYSPROMPT"]
