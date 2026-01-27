# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Charon Labs

"""Sentiment analysis actions for the Customer Support swarm."""

import json
import re
import uuid
from datetime import datetime, UTC
from typing import Any

from mail import action

# Sentiment indicators with associated scores
POSITIVE_INDICATORS = {
    "strong": [
        ("love", 0.9),
        ("amazing", 0.85),
        ("excellent", 0.85),
        ("fantastic", 0.85),
        ("wonderful", 0.8),
        ("great", 0.75),
        ("awesome", 0.8),
        ("perfect", 0.85),
        ("best", 0.75),
        ("thank you so much", 0.8),
        ("really appreciate", 0.75),
    ],
    "moderate": [
        ("good", 0.5),
        ("nice", 0.5),
        ("helpful", 0.6),
        ("thanks", 0.4),
        ("appreciate", 0.5),
        ("pleased", 0.6),
        ("happy", 0.6),
        ("satisfied", 0.5),
        ("works", 0.3),
        ("resolved", 0.5),
        ("fixed", 0.5),
    ],
}

NEGATIVE_INDICATORS = {
    "strong": [
        ("terrible", -0.9),
        ("horrible", -0.9),
        ("worst", -0.85),
        ("hate", -0.85),
        ("disgusted", -0.8),
        ("furious", -0.85),
        ("outraged", -0.85),
        ("scam", -0.9),
        ("fraud", -0.9),
        ("lawsuit", -0.9),
        ("lawyer", -0.8),
        ("sue", -0.85),
        ("unacceptable", -0.75),
        ("ridiculous", -0.7),
    ],
    "moderate": [
        ("frustrated", -0.6),
        ("annoyed", -0.5),
        ("disappointed", -0.5),
        ("upset", -0.55),
        ("angry", -0.65),
        ("bad", -0.5),
        ("poor", -0.5),
        ("awful", -0.7),
        ("useless", -0.6),
        ("broken", -0.4),
        ("failed", -0.45),
        ("doesn't work", -0.5),
        ("not working", -0.5),
        ("can't", -0.3),
    ],
}

ESCALATION_PHRASES = [
    "speak to manager",
    "speak to a manager",
    "talk to manager",
    "supervisor",
    "escalate",
    "cancel my account",
    "cancel my subscription",
    "legal action",
    "lawyer",
    "sue you",
    "report you",
    "bbb",
    "better business bureau",
    "never again",
    "worst company",
    "stealing",
    "theft",
    "refund now",
]

EMOTION_PATTERNS = {
    "anger": ["angry", "furious", "mad", "outraged", "infuriated", "livid"],
    "frustration": ["frustrated", "annoyed", "irritated", "exasperated", "fed up"],
    "disappointment": ["disappointed", "let down", "expected better", "underwhelmed"],
    "anxiety": ["worried", "concerned", "anxious", "nervous", "stressed"],
    "confusion": ["confused", "don't understand", "unclear", "lost", "puzzled"],
    "satisfaction": ["satisfied", "happy", "pleased", "glad", "content"],
    "gratitude": ["thank", "appreciate", "grateful", "thankful"],
}


def _detect_emotions(text: str) -> list[dict[str, Any]]:
    """Detect emotions present in the text."""
    text_lower = text.lower()
    detected = []

    for emotion, patterns in EMOTION_PATTERNS.items():
        for pattern in patterns:
            if pattern in text_lower:
                detected.append(
                    {
                        "emotion": emotion,
                        "indicator": pattern,
                    }
                )
                break  # Only add each emotion once

    return detected


def _calculate_sentiment_score(text: str) -> tuple[float, list[str]]:
    """Calculate sentiment score and return contributing factors."""
    text_lower = text.lower()
    score = 0.0
    factors = []

    # Check positive indicators
    for strength, indicators in POSITIVE_INDICATORS.items():
        for phrase, value in indicators:
            if phrase in text_lower:
                score += value
                factors.append(f"+{value:.1f} ({phrase})")

    # Check negative indicators
    for strength, indicators in NEGATIVE_INDICATORS.items():
        for phrase, value in indicators:
            if phrase in text_lower:
                score += value
                factors.append(f"{value:.1f} ({phrase})")

    # Normalize score to -1 to +1 range
    if score > 1.0:
        score = 1.0
    elif score < -1.0:
        score = -1.0

    return round(score, 2), factors


def _check_escalation_needed(text: str, score: float) -> tuple[bool, str | None]:
    """Check if escalation to human agent is needed."""
    text_lower = text.lower()

    # Check for explicit escalation phrases
    for phrase in ESCALATION_PHRASES:
        if phrase in text_lower:
            return (
                True,
                f"Customer explicitly requested escalation or used concerning phrase: '{phrase}'",
            )

    # Check for very negative sentiment
    if score <= -0.6:
        return True, f"Very negative sentiment detected (score: {score})"

    # Check for strong negative emotions
    if any(
        word in text_lower
        for word in ["furious", "outraged", "lawsuit", "lawyer", "sue"]
    ):
        return True, "Strong negative emotions or legal language detected"

    return False, None


ANALYZE_SENTIMENT_PARAMETERS = {
    "type": "object",
    "properties": {
        "text": {
            "type": "string",
            "description": "The customer text to analyze for sentiment",
        },
    },
    "required": ["text"],
}


@action(
    name="analyze_sentiment",
    description="Analyze the sentiment and emotional tone of customer text.",
    parameters=ANALYZE_SENTIMENT_PARAMETERS,
)
async def analyze_sentiment(args: dict[str, Any]) -> str:
    """Analyze sentiment of customer text."""
    try:
        text = args["text"]
    except KeyError as e:
        return f"Error: {e} is required"

    if not text.strip():
        return json.dumps({"error": "Text cannot be empty"})

    # Calculate sentiment score
    score, factors = _calculate_sentiment_score(text)

    # Determine overall sentiment category
    if score >= 0.3:
        sentiment = "positive"
    elif score <= -0.3:
        sentiment = "negative"
    else:
        sentiment = "neutral"

    # Detect specific emotions
    emotions = _detect_emotions(text)

    # Check if escalation is needed
    escalation_needed, escalation_reason = _check_escalation_needed(text, score)

    result = {
        "sentiment": sentiment,
        "score": score,
        "score_factors": factors
        if factors
        else ["No strong sentiment indicators found"],
        "emotions_detected": emotions
        if emotions
        else [{"emotion": "neutral", "indicator": "none detected"}],
        "escalation_recommended": escalation_needed,
        "escalation_reason": escalation_reason,
        "analysis_summary": _generate_summary(
            sentiment, score, emotions, escalation_needed
        ),
    }

    return json.dumps(result)


def _generate_summary(
    sentiment: str, score: float, emotions: list[dict], escalation: bool
) -> str:
    """Generate a human-readable summary of the sentiment analysis."""
    summary_parts = []

    # Sentiment description
    if score >= 0.5:
        summary_parts.append("Customer expresses strong positive sentiment")
    elif score >= 0.2:
        summary_parts.append("Customer expresses mild positive sentiment")
    elif score <= -0.5:
        summary_parts.append("Customer expresses strong negative sentiment")
    elif score <= -0.2:
        summary_parts.append("Customer expresses mild negative sentiment")
    else:
        summary_parts.append("Customer sentiment is neutral")

    # Emotion summary
    if emotions:
        emotion_names = [e["emotion"] for e in emotions]
        if len(emotion_names) == 1:
            summary_parts.append(f"Primary emotion detected: {emotion_names[0]}")
        elif len(emotion_names) > 1:
            summary_parts.append(f"Emotions detected: {', '.join(emotion_names)}")

    # Escalation note
    if escalation:
        summary_parts.append(
            "ESCALATION RECOMMENDED - Human agent intervention suggested"
        )

    return ". ".join(summary_parts) + "."


CREATE_ESCALATION_PARAMETERS = {
    "type": "object",
    "properties": {
        "ticket_id": {
            "type": "string",
            "description": "The ticket ID to escalate",
        },
        "reason": {
            "type": "string",
            "description": "The reason for escalation",
        },
        "priority": {
            "type": "string",
            "enum": ["high", "urgent"],
            "description": "The escalation priority level",
        },
    },
    "required": ["ticket_id", "reason", "priority"],
}


@action(
    name="create_escalation",
    description="Create an escalation record to flag a ticket for human agent review.",
    parameters=CREATE_ESCALATION_PARAMETERS,
)
async def create_escalation(args: dict[str, Any]) -> str:
    """Create an escalation record for a support ticket."""
    try:
        ticket_id = args["ticket_id"]
        reason = args["reason"]
        priority = args["priority"]
    except KeyError as e:
        return f"Error: {e} is required"

    if priority not in ("high", "urgent"):
        return json.dumps({"error": "Priority must be 'high' or 'urgent'"})

    # Generate escalation record (dummy implementation)
    escalation = {
        "escalation_id": f"ESC-{uuid.uuid4().hex[:8].upper()}",
        "ticket_id": ticket_id,
        "reason": reason,
        "priority": priority,
        "status": "pending",
        "created_at": datetime.now(UTC).isoformat(),
        "assigned_to": "support_supervisor_queue"
        if priority == "high"
        else "urgent_response_team",
        "sla_target": "4 hours" if priority == "high" else "1 hour",
    }

    return json.dumps(
        {
            "success": True,
            "message": f"Escalation created successfully with {priority} priority",
            "escalation": escalation,
        }
    )
