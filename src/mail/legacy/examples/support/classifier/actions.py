# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Charon Labs

"""Ticket classification action for the Customer Support swarm."""

import json
import re
from typing import Any

from mail import action

# Keyword mappings for classification
CATEGORY_KEYWORDS = {
    "billing": [
        "payment",
        "pay",
        "charge",
        "charged",
        "invoice",
        "bill",
        "refund",
        "subscription",
        "cancel",
        "price",
        "pricing",
        "cost",
        "credit card",
        "card",
        "money",
        "fee",
        "upgrade",
        "downgrade",
        "renew",
        "renewal",
    ],
    "technical": [
        "bug",
        "error",
        "crash",
        "not working",
        "broken",
        "issue",
        "problem",
        "feature",
        "slow",
        "loading",
        "api",
        "integration",
        "code",
        "export",
        "import",
        "sync",
        "download",
        "upload",
        "connect",
        "connection",
    ],
    "account": [
        "login",
        "password",
        "reset",
        "account",
        "profile",
        "email",
        "locked",
        "access",
        "sign in",
        "sign up",
        "register",
        "2fa",
        "authentication",
        "security",
        "verify",
        "verification",
        "username",
        "settings",
    ],
    "general": [
        "question",
        "help",
        "support",
        "information",
        "info",
        "how to",
        "what is",
        "where",
        "when",
        "feedback",
        "suggestion",
        "thanks",
        "thank you",
        "appreciate",
        "curious",
        "wondering",
    ],
}

PRIORITY_KEYWORDS = {
    "urgent": [
        "urgent",
        "emergency",
        "asap",
        "immediately",
        "critical",
        "outage",
        "down",
        "breach",
        "hacked",
        "compromised",
        "lost all",
        "cannot access",
        "locked out",
        "deadline",
        "now",
        "right now",
    ],
    "high": [
        "important",
        "serious",
        "major",
        "significant",
        "blocking",
        "stuck",
        "cannot",
        "can't",
        "unable",
        "frustrated",
        "angry",
        "unacceptable",
        "terrible",
        "awful",
        "horrible",
        "worst",
    ],
    "medium": [
        "issue",
        "problem",
        "help",
        "need",
        "want",
        "would like",
        "please",
        "soon",
        "when",
        "how long",
        "waiting",
        "expected",
    ],
    "low": [
        "question",
        "curious",
        "wondering",
        "just",
        "maybe",
        "might",
        "feedback",
        "suggestion",
        "idea",
        "thanks",
        "fyi",
        "minor",
    ],
}


def _count_keyword_matches(text: str, keywords: list[str]) -> int:
    """Count how many keywords appear in the text."""
    text_lower = text.lower()
    count = 0
    for keyword in keywords:
        # Use word boundary matching for better accuracy
        pattern = r"\b" + re.escape(keyword) + r"\b"
        if re.search(pattern, text_lower):
            count += 1
    return count


def _classify_category(text: str) -> tuple[str, float]:
    """Classify the ticket category based on keyword matching."""
    scores = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        scores[category] = _count_keyword_matches(text, keywords)

    # Find the category with highest score
    max_category = max(scores, key=lambda x: scores[x])
    max_score = scores[max_category]

    # Calculate confidence based on score differential
    total_score = sum(scores.values())
    if total_score == 0:
        return "general", 0.3  # Default to general with low confidence

    confidence = max_score / total_score if total_score > 0 else 0.5
    return max_category, round(confidence, 2)


def _classify_priority(text: str) -> tuple[str, float]:
    """Classify the ticket priority based on keyword matching."""
    scores = {}
    for priority, keywords in PRIORITY_KEYWORDS.items():
        scores[priority] = _count_keyword_matches(text, keywords)

    # Apply priority weighting (urgent keywords should have more weight)
    weighted_scores = {
        "urgent": scores["urgent"] * 4,
        "high": scores["high"] * 3,
        "medium": scores["medium"] * 2,
        "low": scores["low"] * 1,
    }

    # Find the priority with highest weighted score
    max_priority = max(weighted_scores, key=lambda x: weighted_scores[x])
    max_score = weighted_scores[max_priority]

    # Default to medium if no clear signal
    if max_score == 0:
        return "medium", 0.5

    total_score = sum(weighted_scores.values())
    confidence = max_score / total_score if total_score > 0 else 0.5
    return max_priority, round(confidence, 2)


CLASSIFY_TICKET_PARAMETERS = {
    "type": "object",
    "properties": {
        "text": {
            "type": "string",
            "description": "The customer support ticket text to classify",
        },
    },
    "required": ["text"],
}


@action(
    name="classify_ticket",
    description="Classify a customer support ticket by category and priority level.",
    parameters=CLASSIFY_TICKET_PARAMETERS,
)
async def classify_ticket(args: dict[str, Any]) -> str:
    """Classify a support ticket and return category and priority."""
    try:
        text = args["text"]
    except KeyError as e:
        return f"Error: {e} is required"

    if not text.strip():
        return json.dumps({"error": "Ticket text cannot be empty"})

    # Perform classification
    category, category_confidence = _classify_category(text)
    priority, priority_confidence = _classify_priority(text)

    # Generate reasoning
    reasoning_parts = []
    if category_confidence >= 0.6:
        reasoning_parts.append(f"Strong match for '{category}' category")
    else:
        reasoning_parts.append(f"Moderate match for '{category}' category")

    if priority == "urgent":
        reasoning_parts.append("Contains urgent/critical language")
    elif priority == "high":
        reasoning_parts.append(
            "Indicates significant user frustration or blocking issue"
        )
    elif priority == "low":
        reasoning_parts.append("Appears to be a general inquiry or minor issue")

    result = {
        "category": category,
        "category_confidence": category_confidence,
        "priority": priority,
        "priority_confidence": priority_confidence,
        "reasoning": ". ".join(reasoning_parts) + ".",
        "suggested_actions": _get_suggested_actions(category, priority),
    }

    return json.dumps(result)


def _get_suggested_actions(category: str, priority: str) -> list[str]:
    """Get suggested actions based on classification."""
    actions = []

    if priority == "urgent":
        actions.append("Escalate to senior support immediately")
        actions.append("Consider immediate callback if phone available")
    elif priority == "high":
        actions.append("Prioritize in support queue")
        actions.append("Provide detailed response within 4 hours")

    if category == "billing":
        actions.append("Check customer's billing history")
        actions.append("Verify subscription status")
    elif category == "technical":
        actions.append("Check for known issues or outages")
        actions.append("Gather technical details if needed")
    elif category == "account":
        actions.append("Verify customer identity")
        actions.append("Check account security flags")

    if not actions:
        actions.append("Respond with standard FAQ or support resources")

    return actions
