# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Charon Labs

"""Summarizer agent for the Research Assistant swarm."""

from mail.legacy.examples.research.summarizer.agent import LiteLLMSummarizerFunction
from mail.legacy.examples.research.summarizer.actions import (
    summarize_text,
    create_bibliography,
)
from mail.legacy.examples.research.summarizer.prompts import SYSPROMPT

__all__ = [
    "LiteLLMSummarizerFunction",
    "summarize_text",
    "create_bibliography",
    "SYSPROMPT",
]
