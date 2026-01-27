# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Charon Labs

"""Verification actions for the Research Assistant swarm."""

import hashlib
import json
from random import Random
from typing import Any

from mail import action

# Source reliability ratings
SOURCE_RELIABILITY = {
    "wikipedia": 0.8,
    "academic": 0.9,
    "news": 0.6,
    "general": 0.5,
    "unknown": 0.3,
}

# Keywords that indicate verifiable facts
VERIFIABLE_INDICATORS = [
    "percent",
    "%",
    "million",
    "billion",
    "year",
    "date",
    "according to",
    "research",
    "study",
    "report",
    "data",
    "survey",
    "analysis",
    "measured",
    "recorded",
    "documented",
]

# Keywords that indicate subjective claims
SUBJECTIVE_INDICATORS = [
    "best",
    "worst",
    "most",
    "should",
    "could",
    "might",
    "believe",
    "think",
    "opinion",
    "feel",
    "seems",
    "appears",
    "probably",
    "possibly",
    "arguably",
    "supposedly",
]


def _analyze_claim_verifiability(claim: str) -> dict[str, Any]:
    """Analyze how verifiable a claim is based on its content."""
    claim_lower = claim.lower()

    verifiable_count = sum(1 for ind in VERIFIABLE_INDICATORS if ind in claim_lower)
    subjective_count = sum(1 for ind in SUBJECTIVE_INDICATORS if ind in claim_lower)

    if subjective_count > verifiable_count:
        claim_type = "opinion"
        verifiability = 0.3
    elif verifiable_count > 0:
        claim_type = "factual"
        verifiability = min(0.9, 0.5 + verifiable_count * 0.1)
    else:
        claim_type = "statement"
        verifiability = 0.5

    return {
        "claim_type": claim_type,
        "verifiability_score": verifiability,
        "verifiable_indicators": verifiable_count,
        "subjective_indicators": subjective_count,
    }


def _check_source_support(
    claim: str, sources: list[str], rng: Random
) -> dict[str, Any]:
    """Check how well sources support a claim."""
    if not sources:
        return {
            "support_level": "unknown",
            "supporting_sources": 0,
            "contradicting_sources": 0,
            "neutral_sources": 0,
        }

    supporting = 0
    contradicting = 0
    neutral = 0

    for source in sources:
        # Simulate source checking based on deterministic randomness
        source_seed = hashlib.md5((claim + source).encode()).hexdigest()
        source_rng = Random(source_seed)

        support_roll = source_rng.random()
        if support_roll > 0.7:
            supporting += 1
        elif support_roll < 0.2:
            contradicting += 1
        else:
            neutral += 1

    total = len(sources)
    support_ratio = supporting / total if total > 0 else 0

    if support_ratio >= 0.6:
        support_level = "supported"
    elif contradicting > supporting:
        support_level = "disputed"
    else:
        support_level = "inconclusive"

    return {
        "support_level": support_level,
        "supporting_sources": supporting,
        "contradicting_sources": contradicting,
        "neutral_sources": neutral,
        "support_ratio": round(support_ratio, 2),
    }


VERIFY_CLAIM_PARAMETERS = {
    "type": "object",
    "properties": {
        "claim": {
            "type": "string",
            "description": "The claim or statement to verify",
        },
        "sources": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of source URLs or references to check against",
        },
    },
    "required": ["claim"],
}


@action(
    name="verify_claim",
    description="Verify a claim by checking it against provided sources.",
    parameters=VERIFY_CLAIM_PARAMETERS,
)
async def verify_claim(args: dict[str, Any]) -> str:
    """Verify a claim against sources."""
    try:
        claim = args["claim"]
        sources = args.get("sources", [])
    except KeyError as e:
        return f"Error: {e} is required"

    if not claim.strip():
        return json.dumps({"error": "Claim cannot be empty"})

    # Analyze the claim
    claim_analysis = _analyze_claim_verifiability(claim)

    # Generate deterministic results
    seed = hashlib.md5(claim.encode()).hexdigest()
    rng = Random(seed)

    # Check source support
    source_check = _check_source_support(claim, sources, rng)

    # Determine verification status
    if claim_analysis["claim_type"] == "opinion":
        status = "not_verifiable"
        explanation = (
            "This appears to be a subjective opinion rather than a verifiable fact."
        )
    elif not sources:
        status = "unverified"
        explanation = "No sources provided for verification. Additional sources needed."
    elif source_check["support_level"] == "supported":
        status = "verified"
        explanation = f"Claim is supported by {source_check['supporting_sources']} of {len(sources)} sources."
    elif source_check["support_level"] == "disputed":
        status = "disputed"
        explanation = (
            f"Claim is contradicted by {source_check['contradicting_sources']} sources."
        )
    else:
        status = "inconclusive"
        explanation = "Sources provide mixed or insufficient evidence."

    result = {
        "claim": claim,
        "status": status,
        "explanation": explanation,
        "claim_analysis": claim_analysis,
        "source_analysis": source_check,
        "sources_checked": len(sources),
        "recommendation": _get_recommendation(status, source_check),
    }

    return json.dumps(result)


def _get_recommendation(status: str, source_check: dict) -> str:
    """Generate a recommendation based on verification results."""
    if status == "verified":
        return "Claim can be cited with attribution to supporting sources."
    elif status == "disputed":
        return "Present both sides of the evidence when citing this claim."
    elif status == "not_verifiable":
        return "Present as opinion or perspective, not as fact."
    elif status == "unverified":
        return "Seek additional sources before citing this claim."
    else:
        return "Exercise caution; more evidence needed for confident citation."


RATE_CONFIDENCE_PARAMETERS = {
    "type": "object",
    "properties": {
        "claim": {
            "type": "string",
            "description": "The claim being evaluated",
        },
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "source_type": {"type": "string"},
                    "supports": {"type": "boolean"},
                },
            },
            "description": "Array of evidence items with source info and support status",
        },
    },
    "required": ["claim", "evidence"],
}


@action(
    name="rate_confidence",
    description="Rate confidence level in a claim based on evidence quality.",
    parameters=RATE_CONFIDENCE_PARAMETERS,
)
async def rate_confidence(args: dict[str, Any]) -> str:
    """Rate confidence in a claim based on evidence."""
    try:
        claim = args["claim"]
        evidence = args["evidence"]
    except KeyError as e:
        return f"Error: {e} is required"

    if not claim.strip():
        return json.dumps({"error": "Claim cannot be empty"})

    if not evidence:
        return json.dumps(
            {
                "claim": claim,
                "confidence_level": "very_low",
                "confidence_score": 0.1,
                "reason": "No evidence provided",
                "evidence_count": 0,
            }
        )

    # Calculate weighted confidence based on evidence
    total_weight: float = 0.0
    support_weight: float = 0.0

    for item in evidence:
        source_type = item.get("source_type", "unknown")
        reliability = SOURCE_RELIABILITY.get(source_type, SOURCE_RELIABILITY["unknown"])
        supports = item.get("supports", False)

        total_weight += float(reliability)
        if supports:
            support_weight += float(reliability)

    if total_weight == 0:
        confidence_score = 0.1
    else:
        confidence_score = support_weight / total_weight

    # Adjust for evidence quantity
    evidence_bonus = min(0.2, len(evidence) * 0.05)
    confidence_score = min(1.0, confidence_score + evidence_bonus)

    # Determine level
    if confidence_score >= 0.8:
        level = "high"
    elif confidence_score >= 0.5:
        level = "medium"
    elif confidence_score >= 0.2:
        level = "low"
    else:
        level = "very_low"

    # Count evidence
    supporting = sum(1 for e in evidence if e.get("supports", False))
    contradicting = len(evidence) - supporting

    result = {
        "claim": claim,
        "confidence_level": level,
        "confidence_score": round(confidence_score, 2),
        "evidence_count": len(evidence),
        "supporting_evidence": supporting,
        "contradicting_evidence": contradicting,
        "reason": _get_confidence_reason(level, supporting, contradicting),
        "reliability_note": "Confidence weighted by source reliability (academic > news > general)",
    }

    return json.dumps(result)


def _get_confidence_reason(level: str, supporting: int, contradicting: int) -> str:
    """Generate explanation for confidence level."""
    if level == "high":
        return f"Strong evidence from {supporting} reliable source(s) with minimal contradiction."
    elif level == "medium":
        return f"Moderate evidence with {supporting} supporting and {contradicting} contradicting source(s)."
    elif level == "low":
        return f"Limited supporting evidence; {contradicting} source(s) present contradictory information."
    else:
        return "Insufficient or unreliable evidence to support this claim."
