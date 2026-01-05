# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Charon Labs

"""Researcher agent for the Research Assistant swarm."""

from mail.examples.research.researcher.agent import LiteLLMResearcherFunction
from mail.examples.research.researcher.prompts import SYSPROMPT

__all__ = ["LiteLLMResearcherFunction", "SYSPROMPT"]
