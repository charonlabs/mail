# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Charon Labs

"""Verifier agent for the Research Assistant swarm."""

from mail.legacy.examples.research.verifier.agent import LiteLLMVerifierFunction
from mail.legacy.examples.research.verifier.actions import verify_claim, rate_confidence
from mail.legacy.examples.research.verifier.prompts import SYSPROMPT

__all__ = ["LiteLLMVerifierFunction", "verify_claim", "rate_confidence", "SYSPROMPT"]
