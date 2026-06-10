# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Charon Labs

"""Customer Support example swarm.

This swarm demonstrates multi-agent workflows for handling customer inquiries
with ticket classification, FAQ search, sentiment analysis, and escalation.

Agents:
    - coordinator: Entry point that routes queries and synthesizes responses
    - faq: Searches FAQ database for relevant answers
    - classifier: Classifies tickets by category and priority
    - sentiment: Analyzes customer sentiment and flags escalations
"""

from mail.legacy.examples.support.coordinator.agent import LiteLLMCoordinatorFunction
from mail.legacy.examples.support.faq.agent import LiteLLMFaqFunction
from mail.legacy.examples.support.faq.actions import search_faq
from mail.legacy.examples.support.classifier.agent import LiteLLMClassifierFunction
from mail.legacy.examples.support.classifier.actions import classify_ticket
from mail.legacy.examples.support.sentiment.agent import LiteLLMSentimentFunction
from mail.legacy.examples.support.sentiment.actions import analyze_sentiment, create_escalation

__all__ = [
    "LiteLLMCoordinatorFunction",
    "LiteLLMFaqFunction",
    "LiteLLMClassifierFunction",
    "LiteLLMSentimentFunction",
    "search_faq",
    "classify_ticket",
    "analyze_sentiment",
    "create_escalation",
]
