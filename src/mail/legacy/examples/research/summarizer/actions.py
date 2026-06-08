# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Charon Labs

"""Summarization actions for the Research Assistant swarm."""

import json
import re
from datetime import datetime, UTC
from typing import Any

from mail import action


def _extract_sentences(text: str) -> list[str]:
    """Extract sentences from text."""
    # Simple sentence splitting
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sentences if len(s.strip()) > 10]


def _score_sentence_importance(sentence: str, all_sentences: list[str]) -> float:
    """Score sentence importance based on content features."""
    score = 0.0
    sentence_lower = sentence.lower()

    # Position bonus (first sentences are often important)
    if sentence in all_sentences[:3]:
        score += 0.3

    # Contains important indicators
    importance_words = [
        "important",
        "key",
        "main",
        "significant",
        "primary",
        "crucial",
        "essential",
        "critical",
        "major",
        "notable",
        "first",
        "second",
        "third",
        "finally",
        "however",
        "therefore",
        "in conclusion",
        "as a result",
        "research shows",
        "data indicates",
    ]
    for word in importance_words:
        if word in sentence_lower:
            score += 0.2

    # Contains numbers (often factual/important)
    if any(char.isdigit() for char in sentence):
        score += 0.15

    # Length penalty for very short or very long sentences
    word_count = len(sentence.split())
    if word_count < 5:
        score -= 0.2
    elif word_count > 50:
        score -= 0.1
    elif 15 <= word_count <= 30:
        score += 0.1

    return max(0, score)


def _create_extractive_summary(text: str, max_sentences: int) -> str:
    """Create an extractive summary by selecting important sentences."""
    sentences = _extract_sentences(text)

    if len(sentences) <= max_sentences:
        return " ".join(sentences)

    # Score sentences
    scored = [(s, _score_sentence_importance(s, sentences)) for s in sentences]

    # Sort by score but maintain some original order
    # Take top-scoring sentences
    scored.sort(key=lambda x: x[1], reverse=True)
    selected = scored[:max_sentences]

    # Reorder by original position
    selected_sentences = [s[0] for s in selected]
    ordered = [s for s in sentences if s in selected_sentences]

    return " ".join(ordered)


SUMMARIZE_TEXT_PARAMETERS = {
    "type": "object",
    "properties": {
        "text": {
            "type": "string",
            "description": "The text to summarize",
        },
        "max_length": {
            "type": "integer",
            "minimum": 50,
            "maximum": 2000,
            "description": "Maximum length of summary in characters (default: 500)",
        },
    },
    "required": ["text"],
}


@action(
    name="summarize_text",
    description="Create a concise summary of longer text.",
    parameters=SUMMARIZE_TEXT_PARAMETERS,
)
async def summarize_text(args: dict[str, Any]) -> str:
    """Summarize text to specified length."""
    try:
        text = args["text"]
        max_length = args.get("max_length", 500)
    except KeyError as e:
        return f"Error: {e} is required"

    if not text.strip():
        return json.dumps({"error": "Text cannot be empty"})

    original_length = len(text)
    original_sentences = len(_extract_sentences(text))

    # Estimate needed sentences for target length
    avg_sentence_length = original_length / max(original_sentences, 1)
    target_sentences = max(1, int(max_length / max(avg_sentence_length, 50)))

    # Create summary
    summary = _create_extractive_summary(text, target_sentences)

    # Truncate if still too long
    if len(summary) > max_length:
        summary = summary[: max_length - 3].rsplit(" ", 1)[0] + "..."

    compression_ratio = len(summary) / original_length if original_length > 0 else 1

    result = {
        "summary": summary,
        "original_length": original_length,
        "summary_length": len(summary),
        "compression_ratio": round(compression_ratio, 2),
        "original_sentences": original_sentences,
        "summary_sentences": len(_extract_sentences(summary)),
        "method": "extractive",
    }

    return json.dumps(result)


CREATE_BIBLIOGRAPHY_PARAMETERS = {
    "type": "object",
    "properties": {
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "author": {"type": "string"},
                    "url": {"type": "string"},
                    "date": {"type": "string"},
                    "source_type": {"type": "string"},
                },
            },
            "description": "Array of source objects with title, author, url, date, source_type",
        },
        "style": {
            "type": "string",
            "enum": ["apa", "mla", "chicago", "simple"],
            "description": "Citation style (default: simple)",
        },
    },
    "required": ["sources"],
}


@action(
    name="create_bibliography",
    description="Format sources into a properly formatted bibliography.",
    parameters=CREATE_BIBLIOGRAPHY_PARAMETERS,
)
async def create_bibliography(args: dict[str, Any]) -> str:
    """Create a formatted bibliography from sources."""
    try:
        sources = args["sources"]
        style = args.get("style", "simple")
    except KeyError as e:
        return f"Error: {e} is required"

    if not sources:
        return json.dumps({"error": "At least one source is required"})

    formatted_entries = []

    for i, source in enumerate(sources, 1):
        title = source.get("title", "Untitled")
        author = source.get("author", "Unknown Author")
        url = source.get("url", "")
        date = source.get("date", "n.d.")
        source_type = source.get("source_type", "web")

        if style == "apa":
            # APA style: Author. (Date). Title. URL
            entry = f"{author}. ({date}). {title}."
            if url:
                entry += f" Retrieved from {url}"
        elif style == "mla":
            # MLA style: Author. "Title." Date. URL.
            entry = f'{author}. "{title}." {date}.'
            if url:
                entry += f" {url}."
        elif style == "chicago":
            # Chicago style: Author. "Title." Accessed Date. URL.
            entry = f'{author}. "{title}."'
            if url:
                entry += f" Accessed {datetime.now(UTC).strftime('%B %d, %Y')}. {url}."
        else:  # simple
            # Simple style: numbered list
            entry = f"[{i}] {title}"
            if author != "Unknown Author":
                entry += f" by {author}"
            if date != "n.d.":
                entry += f" ({date})"
            if url:
                entry += f" - {url}"

        formatted_entries.append(
            {
                "index": i,
                "formatted": entry,
                "source_type": source_type,
                "original": source,
            }
        )

    # Create bibliography text
    bibliography_text = "\n".join([e["formatted"] for e in formatted_entries])

    result = {
        "style": style,
        "entry_count": len(formatted_entries),
        "entries": formatted_entries,
        "bibliography": bibliography_text,
        "generated_at": datetime.now(UTC).isoformat(),
    }

    return json.dumps(result)
