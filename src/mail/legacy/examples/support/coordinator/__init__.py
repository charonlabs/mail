# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Charon Labs

"""Coordinator agent for the Customer Support swarm."""

from mail.legacy.examples.support.coordinator.agent import LiteLLMCoordinatorFunction
from mail.legacy.examples.support.coordinator.prompts import SYSPROMPT

__all__ = ["LiteLLMCoordinatorFunction", "SYSPROMPT"]
