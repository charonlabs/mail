# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Charon Labs

"""Classifier agent for the Customer Support swarm."""

from mail.legacy.examples.support.classifier.agent import LiteLLMClassifierFunction
from mail.legacy.examples.support.classifier.actions import classify_ticket
from mail.legacy.examples.support.classifier.prompts import SYSPROMPT

__all__ = ["LiteLLMClassifierFunction", "classify_ticket", "SYSPROMPT"]
