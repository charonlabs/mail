# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Charon Labs

"""Report formatting action for the Data Analysis swarm."""

import json
from datetime import datetime, UTC
from typing import Any

from mail import action


def _format_table(data: list[dict[str, Any]], columns: list[str] | None = None) -> str:
    """Format data as a markdown table."""
    if not data:
        return "_No data available_"

    # Determine columns
    if columns is None:
        columns = list(data[0].keys())

    # Build header
    header = "| " + " | ".join(str(col) for col in columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"

    # Build rows
    rows = []
    for row in data[:50]:  # Limit to 50 rows
        row_values = []
        for col in columns:
            val = row.get(col, "")
            if isinstance(val, float):
                row_values.append(f"{val:.4f}")
            else:
                row_values.append(str(val))
        rows.append("| " + " | ".join(row_values) + " |")

    table = "\n".join([header, separator] + rows)

    if len(data) > 50:
        table += f"\n\n_...and {len(data) - 50} more rows_"

    return table


def _format_statistics_table(metrics: dict[str, Any]) -> str:
    """Format statistics metrics as a table."""
    if not metrics:
        return "_No statistics available_"

    rows = ["| Metric | Value |", "| --- | --- |"]
    for metric, value in metrics.items():
        if isinstance(value, dict):
            if "error" in value:
                rows.append(f"| {metric} | Error: {value['error']} |")
            else:
                rows.append(f"| {metric} | {json.dumps(value)} |")
        elif isinstance(value, float):
            rows.append(f"| {metric} | {value:.4f} |")
        else:
            rows.append(f"| {metric} | {value} |")

    return "\n".join(rows)


def _format_section(section_type: str, content: Any) -> str:
    """Format a single section based on its type."""
    if isinstance(content, str):
        return content

    if isinstance(content, dict):
        if "table" in content:
            return _format_table(content["table"], content.get("columns"))
        if "metrics" in content:
            return _format_statistics_table(content["metrics"])
        if "text" in content:
            return content["text"]
        # Generic dict formatting
        return "\n".join(f"- **{k}**: {v}" for k, v in content.items())

    if isinstance(content, list):
        if all(isinstance(item, dict) for item in content):
            return _format_table(content)
        return "\n".join(f"- {item}" for item in content)

    return str(content)


FORMAT_REPORT_PARAMETERS = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": "The report title",
        },
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "heading": {
                        "type": "string",
                        "description": "Section heading",
                    },
                    "content": {
                        "description": "Section content (string, object, or array)",
                    },
                },
                "required": ["heading", "content"],
            },
            "description": "Array of report sections with heading and content",
        },
    },
    "required": ["title", "sections"],
}


@action(
    name="format_report",
    description="Generate a formatted markdown report with sections, tables, and summaries.",
    parameters=FORMAT_REPORT_PARAMETERS,
)
async def format_report(args: dict[str, Any]) -> str:
    """Format data into a structured markdown report."""
    try:
        title = args["title"]
        sections = args["sections"]
    except KeyError as e:
        return f"Error: {e} is required"

    if not title.strip():
        return json.dumps({"error": "Report title cannot be empty"})

    if not sections:
        return json.dumps({"error": "Report must have at least one section"})

    # Build report
    report_parts = []

    # Title and metadata
    report_parts.append(f"# {title}")
    report_parts.append("")
    report_parts.append(
        f"_Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}_"
    )
    report_parts.append("")
    report_parts.append("---")
    report_parts.append("")

    # Table of contents (if more than 2 sections)
    if len(sections) > 2:
        report_parts.append("## Table of Contents")
        report_parts.append("")
        for i, section in enumerate(sections, 1):
            heading = section.get("heading", f"Section {i}")
            anchor = heading.lower().replace(" ", "-").replace(":", "")
            report_parts.append(f"{i}. [{heading}](#{anchor})")
        report_parts.append("")
        report_parts.append("---")
        report_parts.append("")

    # Sections
    for section in sections:
        heading = section.get("heading", "Untitled Section")
        content = section.get("content", "")

        report_parts.append(f"## {heading}")
        report_parts.append("")
        report_parts.append(_format_section(heading.lower(), content))
        report_parts.append("")

    # Footer
    report_parts.append("---")
    report_parts.append("")
    report_parts.append("_End of Report_")

    report_text = "\n".join(report_parts)

    return json.dumps(
        {
            "success": True,
            "title": title,
            "section_count": len(sections),
            "character_count": len(report_text),
            "report": report_text,
        }
    )
