# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Charon Labs

"""FAQ agent for the Customer Support swarm."""

from mail.legacy.examples.support.faq.agent import LiteLLMFaqFunction
from mail.legacy.examples.support.faq.actions import search_faq
from mail.legacy.examples.support.faq.prompts import SYSPROMPT

__all__ = ["LiteLLMFaqFunction", "search_faq", "SYSPROMPT"]
