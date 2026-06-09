# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Charon Labs

"""Sentiment agent for the Customer Support swarm."""

from mail.legacy.examples.support.sentiment.agent import LiteLLMSentimentFunction
from mail.legacy.examples.support.sentiment.actions import analyze_sentiment, create_escalation
from mail.legacy.examples.support.sentiment.prompts import SYSPROMPT

__all__ = [
    "LiteLLMSentimentFunction",
    "analyze_sentiment",
    "create_escalation",
    "SYSPROMPT",
]
