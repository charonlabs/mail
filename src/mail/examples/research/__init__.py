# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Charon Labs

"""Research Assistant example swarm.

This swarm demonstrates research workflows with information gathering,
fact verification, and summarization. It includes real HTTP integrations
where available with dummy fallbacks.

Agents:
    - researcher: Entry point that coordinates research tasks
    - searcher: Searches for information on topics
    - verifier: Cross-references and verifies claims
    - summarizer: Synthesizes and summarizes findings
"""

from mail.examples.research.researcher.agent import LiteLLMResearcherFunction
from mail.examples.research.searcher.agent import LiteLLMSearcherFunction
from mail.examples.research.searcher.actions import search_topic, extract_facts
from mail.examples.research.verifier.agent import LiteLLMVerifierFunction
from mail.examples.research.verifier.actions import verify_claim, rate_confidence
from mail.examples.research.summarizer.agent import LiteLLMSummarizerFunction
from mail.examples.research.summarizer.actions import (
    summarize_text,
    create_bibliography,
)

__all__ = [
    "LiteLLMResearcherFunction",
    "LiteLLMSearcherFunction",
    "LiteLLMVerifierFunction",
    "LiteLLMSummarizerFunction",
    "search_topic",
    "extract_facts",
    "verify_claim",
    "rate_confidence",
    "summarize_text",
    "create_bibliography",
]
