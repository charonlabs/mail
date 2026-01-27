# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Charon Labs

"""Search actions for the Research Assistant swarm.

This module includes dummy search implementations that simulate
real search results. In a production environment, these could be
replaced with actual API integrations.
"""

import json
import hashlib
from datetime import datetime, timedelta, UTC
from random import Random
from typing import Any

from mail import action

# Simulated knowledge base for different source types
KNOWLEDGE_BASE = {
    "wikipedia": {
        "topics": {
            "artificial intelligence": {
                "summary": "Artificial intelligence (AI) is intelligence demonstrated by machines, as opposed to natural intelligence displayed by animals including humans.",
                "facts": [
                    "AI was founded as an academic discipline in 1956",
                    "Machine learning is a subset of AI that enables systems to learn from data",
                    "Deep learning uses neural networks with many layers",
                    "AI applications include natural language processing, computer vision, and robotics",
                ],
                "url": "https://en.wikipedia.org/wiki/Artificial_intelligence",
            },
            "climate change": {
                "summary": "Climate change refers to long-term shifts in temperatures and weather patterns, mainly caused by human activities since the 1800s.",
                "facts": [
                    "Global average temperature has risen about 1.1°C since pre-industrial times",
                    "The main driver is burning fossil fuels (coal, oil, gas)",
                    "Effects include rising sea levels, extreme weather, and ecosystem disruption",
                    "The Paris Agreement aims to limit warming to 1.5°C above pre-industrial levels",
                ],
                "url": "https://en.wikipedia.org/wiki/Climate_change",
            },
            "python programming": {
                "summary": "Python is a high-level, general-purpose programming language known for its readability and versatility.",
                "facts": [
                    "Python was created by Guido van Rossum and released in 1991",
                    "Python emphasizes code readability with significant indentation",
                    "It supports multiple programming paradigms including procedural, object-oriented, and functional",
                    "Python is widely used in web development, data science, AI, and automation",
                ],
                "url": "https://en.wikipedia.org/wiki/Python_(programming_language)",
            },
        },
    },
    "academic": {
        "topics": {
            "artificial intelligence": {
                "summary": "Recent advances in artificial intelligence have transformed multiple industries through improved algorithms and increased computational power.",
                "facts": [
                    "Transformer architecture (2017) revolutionized NLP and led to large language models",
                    "GPT-4 and similar models demonstrate emergent capabilities not present in smaller models",
                    "AI safety research focuses on alignment, interpretability, and robustness",
                    "Benchmark performance on many tasks now exceeds human-level performance",
                ],
                "url": "https://arxiv.org/abs/ai-research",
            },
            "climate change": {
                "summary": "Climate science research indicates accelerating impacts and the need for rapid decarbonization.",
                "facts": [
                    "IPCC AR6 report (2021-2023) provides comprehensive assessment of climate science",
                    "Carbon budget for 1.5°C is estimated at 400-500 GtCO2 from 2020",
                    "Climate tipping points may be reached at lower temperatures than previously thought",
                    "Methane emissions reduction offers near-term climate benefits",
                ],
                "url": "https://www.ipcc.ch/reports/",
            },
        },
    },
    "news": {
        "topics": {
            "artificial intelligence": {
                "summary": "AI developments continue to make headlines with new applications and policy discussions.",
                "facts": [
                    "Major tech companies are investing billions in AI research and deployment",
                    "Governments worldwide are developing AI regulations and policies",
                    "AI-generated content is becoming increasingly prevalent",
                    "Concerns about job displacement and misinformation persist",
                ],
                "url": "https://news.example.com/ai-developments",
            },
            "climate change": {
                "summary": "Climate news focuses on extreme weather events and policy developments.",
                "facts": [
                    "Record temperatures and extreme weather events reported globally",
                    "COP climate conferences continue to set emissions targets",
                    "Renewable energy adoption is accelerating worldwide",
                    "Corporate sustainability commitments increasing but scrutinized for greenwashing",
                ],
                "url": "https://news.example.com/climate-news",
            },
        },
    },
}


def _generate_search_results(query: str, source: str, rng: Random) -> dict[str, Any]:
    """Generate search results based on query and source."""
    query_lower = query.lower()

    # Check if query matches known topics
    source_data = KNOWLEDGE_BASE.get(source, KNOWLEDGE_BASE.get("wikipedia", {}))
    topics = source_data.get("topics", {})

    matched_topic = None
    best_match_score = 0

    for topic_name, topic_data in topics.items():
        # Simple keyword matching
        topic_words = set(topic_name.lower().split())
        query_words = set(query_lower.split())
        overlap = len(topic_words & query_words)
        if overlap > best_match_score:
            best_match_score = overlap
            matched_topic = (topic_name, topic_data)

    if matched_topic:
        topic_name, topic_data = matched_topic
        return {
            "query": query,
            "source": source,
            "matched_topic": topic_name,
            "relevance_score": min(0.95, 0.5 + best_match_score * 0.2),
            "summary": topic_data["summary"],
            "facts": topic_data["facts"],
            "url": topic_data["url"],
            "retrieved_at": datetime.now(UTC).isoformat(),
        }

    # Generate generic results for unmatched queries
    return {
        "query": query,
        "source": source,
        "matched_topic": None,
        "relevance_score": 0.3,
        "summary": f"Search results for '{query}' from {source} sources.",
        "facts": [
            f"Information about {query} is available from multiple sources",
            "Further research may be needed for specific details",
            "Consider searching with more specific terms",
        ],
        "url": f"https://search.example.com/{source}?q={query.replace(' ', '+')}",
        "retrieved_at": datetime.now(UTC).isoformat(),
    }


SEARCH_TOPIC_PARAMETERS = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "The search query or topic to research",
        },
        "source": {
            "type": "string",
            "enum": ["wikipedia", "academic", "news", "general"],
            "description": "The type of source to search (default: general)",
        },
    },
    "required": ["query"],
}


@action(
    name="search_topic",
    description="Search for information on a topic from various sources.",
    parameters=SEARCH_TOPIC_PARAMETERS,
)
async def search_topic(args: dict[str, Any]) -> str:
    """Search for information on a topic."""
    try:
        query = args["query"]
        source = args.get("source", "general")
    except KeyError as e:
        return f"Error: {e} is required"

    if not query.strip():
        return json.dumps({"error": "Search query cannot be empty"})

    if source not in ["wikipedia", "academic", "news", "general"]:
        source = "general"

    # Generate deterministic results based on query
    seed = hashlib.md5(query.encode()).hexdigest()
    rng = Random(seed)

    # For "general" source, aggregate from multiple sources
    if source == "general":
        all_results = []
        for src in ["wikipedia", "academic", "news"]:
            result = _generate_search_results(query, src, rng)
            all_results.append(result)

        # Combine results
        combined_facts = []
        for r in all_results:
            combined_facts.extend(r.get("facts", []))

        return json.dumps(
            {
                "query": query,
                "source": "general (aggregated)",
                "result_count": len(all_results),
                "combined_facts": combined_facts[:8],  # Top 8 facts
                "sources": [
                    {
                        "source": r["source"],
                        "url": r["url"],
                        "relevance": r["relevance_score"],
                    }
                    for r in all_results
                ],
                "retrieved_at": datetime.now(UTC).isoformat(),
            }
        )

    results = _generate_search_results(query, source, rng)
    return json.dumps(results)


EXTRACT_FACTS_PARAMETERS = {
    "type": "object",
    "properties": {
        "text": {
            "type": "string",
            "description": "The text to extract facts from",
        },
    },
    "required": ["text"],
}


@action(
    name="extract_facts",
    description="Extract key facts and claims from a block of text.",
    parameters=EXTRACT_FACTS_PARAMETERS,
)
async def extract_facts(args: dict[str, Any]) -> str:
    """Extract key facts from text."""
    try:
        text = args["text"]
    except KeyError as e:
        return f"Error: {e} is required"

    if not text.strip():
        return json.dumps({"error": "Text cannot be empty"})

    # Simple fact extraction based on sentence analysis
    sentences = text.replace("!", ".").replace("?", ".").split(".")
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]

    facts = []
    claims = []

    for sentence in sentences[:10]:  # Limit to first 10 sentences
        sentence_lower = sentence.lower()

        # Identify factual statements (contains numbers, dates, or definitive language)
        is_fact = any(
            [
                any(char.isdigit() for char in sentence),
                any(
                    word in sentence_lower
                    for word in ["is", "are", "was", "were", "has", "have"]
                ),
                any(
                    word in sentence_lower
                    for word in ["according to", "research shows", "studies indicate"]
                ),
            ]
        )

        # Identify claims (subjective or requiring verification)
        is_claim = any(
            [
                any(
                    word in sentence_lower
                    for word in ["should", "could", "might", "may", "probably"]
                ),
                any(
                    word in sentence_lower
                    for word in ["best", "worst", "most", "least"]
                ),
                any(word in sentence_lower for word in ["believe", "think", "opinion"]),
            ]
        )

        if is_claim:
            claims.append(
                {
                    "text": sentence,
                    "type": "claim",
                    "needs_verification": True,
                }
            )
        elif is_fact:
            facts.append(
                {
                    "text": sentence,
                    "type": "fact",
                    "confidence": 0.7,  # Default confidence
                }
            )

    return json.dumps(
        {
            "original_length": len(text),
            "sentences_analyzed": len(sentences),
            "facts_extracted": len(facts),
            "claims_identified": len(claims),
            "facts": facts,
            "claims": claims,
            "extraction_note": "Facts are statements with specific data; claims require verification",
        }
    )
