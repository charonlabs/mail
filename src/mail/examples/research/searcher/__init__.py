# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Charon Labs

"""Searcher agent for the Research Assistant swarm."""

from mail.examples.research.searcher.agent import LiteLLMSearcherFunction
from mail.examples.research.searcher.actions import search_topic, extract_facts
from mail.examples.research.searcher.prompts import SYSPROMPT

__all__ = ["LiteLLMSearcherFunction", "search_topic", "extract_facts", "SYSPROMPT"]
