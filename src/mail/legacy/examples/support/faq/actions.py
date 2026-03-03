# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Charon Labs

"""FAQ search action for the Customer Support swarm."""

import json
from typing import Any

from mail import action

# Dummy FAQ database for demonstration purposes
FAQ_DATABASE = [
    {
        "id": "faq-001",
        "question": "How do I reset my password?",
        "answer": "To reset your password: 1) Go to the login page, 2) Click 'Forgot Password', 3) Enter your email address, 4) Check your email for a reset link, 5) Click the link and create a new password. The reset link expires after 24 hours.",
        "category": "account",
        "keywords": ["password", "reset", "forgot", "login", "account", "access"],
    },
    {
        "id": "faq-002",
        "question": "What is your refund policy?",
        "answer": "We offer a 30-day money-back guarantee on all purchases. To request a refund: 1) Contact our support team within 30 days of purchase, 2) Provide your order number, 3) Explain the reason for the refund. Refunds are processed within 5-7 business days to your original payment method.",
        "category": "billing",
        "keywords": ["refund", "money", "return", "policy", "guarantee", "purchase"],
    },
    {
        "id": "faq-003",
        "question": "How do I cancel my subscription?",
        "answer": "To cancel your subscription: 1) Log into your account, 2) Go to Settings > Subscription, 3) Click 'Cancel Subscription', 4) Confirm your cancellation. Your access continues until the end of the current billing period. You can resubscribe at any time.",
        "category": "billing",
        "keywords": ["cancel", "subscription", "unsubscribe", "stop", "billing"],
    },
    {
        "id": "faq-004",
        "question": "How do I contact customer support?",
        "answer": "You can reach our support team through: 1) Email: support@example.com (response within 24 hours), 2) Live chat on our website (available 9am-6pm EST), 3) Phone: 1-800-EXAMPLE (Monday-Friday 9am-5pm EST). For urgent issues, please use phone support.",
        "category": "general",
        "keywords": ["contact", "support", "help", "phone", "email", "chat"],
    },
    {
        "id": "faq-005",
        "question": "Why is my account locked?",
        "answer": "Accounts may be locked for security reasons including: 1) Multiple failed login attempts, 2) Suspicious activity detected, 3) Password expired. To unlock your account, use the 'Forgot Password' feature or contact support. If you believe this is an error, our security team can review your case.",
        "category": "account",
        "keywords": ["locked", "account", "security", "blocked", "access", "suspended"],
    },
    {
        "id": "faq-006",
        "question": "How do I update my billing information?",
        "answer": "To update billing information: 1) Log into your account, 2) Go to Settings > Payment Methods, 3) Click 'Edit' next to your current payment method or 'Add New', 4) Enter your new card details, 5) Click 'Save'. Your next charge will use the updated payment method.",
        "category": "billing",
        "keywords": ["billing", "payment", "credit card", "update", "change", "card"],
    },
    {
        "id": "faq-007",
        "question": "What features are included in my plan?",
        "answer": "Plan features vary by tier: Basic includes core features and email support. Pro adds advanced analytics, priority support, and API access. Enterprise includes all Pro features plus dedicated account manager, custom integrations, and 24/7 phone support. Visit our pricing page for detailed comparisons.",
        "category": "general",
        "keywords": [
            "features",
            "plan",
            "tier",
            "pricing",
            "include",
            "basic",
            "pro",
            "enterprise",
        ],
    },
    {
        "id": "faq-008",
        "question": "How do I export my data?",
        "answer": "To export your data: 1) Go to Settings > Data & Privacy, 2) Click 'Export Data', 3) Select the data types to include, 4) Choose your format (CSV or JSON), 5) Click 'Generate Export'. You'll receive an email with a download link within 24 hours. Exports are available for 7 days.",
        "category": "technical",
        "keywords": ["export", "data", "download", "backup", "csv", "json"],
    },
    {
        "id": "faq-009",
        "question": "Is my data secure?",
        "answer": "Yes, we take security seriously. We use: 1) AES-256 encryption for data at rest, 2) TLS 1.3 for data in transit, 3) Regular security audits by third parties, 4) SOC 2 Type II certification, 5) GDPR and CCPA compliance. We never sell your data to third parties.",
        "category": "technical",
        "keywords": [
            "security",
            "data",
            "encryption",
            "privacy",
            "secure",
            "safe",
            "gdpr",
        ],
    },
    {
        "id": "faq-010",
        "question": "How do I enable two-factor authentication?",
        "answer": "To enable 2FA: 1) Go to Settings > Security, 2) Click 'Enable Two-Factor Authentication', 3) Choose your method (authenticator app or SMS), 4) Follow the setup instructions, 5) Save your backup codes. We recommend using an authenticator app for better security.",
        "category": "account",
        "keywords": ["two-factor", "2fa", "authentication", "security", "mfa", "otp"],
    },
]

SEARCH_FAQ_PARAMETERS = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "The search query to find relevant FAQ entries",
        },
        "max_results": {
            "type": "integer",
            "description": "Maximum number of FAQ entries to return (default: 3)",
            "minimum": 1,
            "maximum": 10,
        },
    },
    "required": ["query"],
}


def _calculate_relevance(query: str, faq_entry: dict[str, Any]) -> float:
    """Calculate relevance score between query and FAQ entry."""
    query_terms = set(query.lower().split())
    keywords = set(faq_entry.get("keywords", []))
    question_terms = set(faq_entry.get("question", "").lower().split())

    # Score based on keyword matches (highest weight)
    keyword_matches = len(query_terms & keywords)
    # Score based on question word matches
    question_matches = len(query_terms & question_terms)

    # Combined score with weights
    score = (keyword_matches * 2.0) + (question_matches * 1.0)
    return score


@action(
    name="search_faq",
    description="Search the FAQ database for entries relevant to a customer query.",
    parameters=SEARCH_FAQ_PARAMETERS,
)
async def search_faq(args: dict[str, Any]) -> str:
    """Search the FAQ database and return relevant entries."""
    try:
        query = args["query"]
        max_results = args.get("max_results", 3)
    except KeyError as e:
        return f"Error: {e} is required"

    if not query.strip():
        return json.dumps({"error": "Query cannot be empty", "results": []})

    # Calculate relevance scores for all FAQ entries
    scored_entries = []
    for entry in FAQ_DATABASE:
        score = _calculate_relevance(query, entry)
        if score > 0:
            scored_entries.append((score, entry))

    # Sort by relevance score (descending)
    scored_entries.sort(key=lambda x: x[0], reverse=True)

    # Take top results
    results = []
    for score, entry in scored_entries[:max_results]:
        results.append(
            {
                "id": entry["id"],
                "question": entry["question"],
                "answer": entry["answer"],
                "category": entry["category"],
                "relevance_score": round(score, 2),
            }
        )

    return json.dumps(
        {
            "query": query,
            "total_matches": len(scored_entries),
            "results_returned": len(results),
            "results": results,
        }
    )
