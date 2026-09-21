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

from mail.legacy.examples.research.researcher.agent import LiteLLMResearcherFunction
from mail.legacy.examples.research.searcher.actions import extract_facts, search_topic
from mail.legacy.examples.research.searcher.agent import LiteLLMSearcherFunction
from mail.legacy.examples.research.summarizer.actions import (
    create_bibliography,
    summarize_text,
)
from mail.legacy.examples.research.summarizer.agent import LiteLLMSummarizerFunction
from mail.legacy.examples.research.verifier.actions import rate_confidence, verify_claim
from mail.legacy.examples.research.verifier.agent import LiteLLMVerifierFunction

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
