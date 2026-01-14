"""
Task Summarizer using MAIL.

Generates short titles (max 6 words) for conversation tasks using Haiku.
Uses the breakpoint tool pattern for structured output.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from mail import MAILAction, MAILAgentTemplate, MAILSwarmTemplate
from mail.factories import LiteLLMSupervisorFunction

if TYPE_CHECKING:
    from mail import MAILSwarm


# ============================================================================
# Tool Definition: submit_title
# ============================================================================

class SubmitTitleArgs(BaseModel):
    """Arguments for the submit_title tool."""
    title: str = Field(
        description="A concise title for the conversation (maximum 6 words)",
        max_length=50,
    )


async def _submit_title_fn(args: dict) -> str:
    """
    Submit a title. This is a breakpoint tool - execution pauses here
    and the args are returned to the caller for processing.
    """
    return json.dumps({"status": "submitted", "title": args.get("title", "")})


submit_title_action = MAILAction.from_pydantic_model(
    model=SubmitTitleArgs,
    function=_submit_title_fn,
    name="submit_title",
    description="Submit a short title (max 6 words) summarizing the conversation.",
)


# ============================================================================
# System prompt
# ============================================================================

SYSTEM_PROMPT = """You are a title generator. Given a conversation between a user and an AI assistant, generate a concise title that captures the main topic or request.

Rules:
- Maximum 6 words
- Be specific and descriptive
- Use title case
- No quotes or punctuation at the end
- Focus on what the user wanted, not what the assistant did

Examples:
- "Weather Forecast for Tokyo"
- "Debug Python Import Error"
- "Explain Quantum Entanglement"
- "Create React Login Form"
"""


# ============================================================================
# TaskSummarizer class
# ============================================================================

class TaskSummarizer:
    """
    Generates short titles for conversation tasks.

    Uses Haiku for fast, cheap summarization with structured output
    via the breakpoint tool pattern.

    Example:
        summarizer = TaskSummarizer()

        messages = [
            {"role": "user", "content": "What's the weather in Tokyo?"},
            {"role": "assistant", "content": "The weather in Tokyo is..."},
        ]

        title = await summarizer.summarize(messages)
        # Returns: "Tokyo Weather Forecast"

        await summarizer.shutdown()
    """

    def __init__(self, model: str = "anthropic/claude-haiku-4-5-20251001"):
        self.model = model
        self._swarm: MAILSwarm | None = None
        self._template = self._create_template()

    def _create_template(self) -> MAILSwarmTemplate:
        """Create the MAIL swarm template with submit_title as breakpoint tool."""
        agent = MAILAgentTemplate(
            name="summarizer",
            factory=LiteLLMSupervisorFunction,
            comm_targets=[],
            actions=[submit_title_action],
            agent_params={
                "llm": self.model,
                "system": SYSTEM_PROMPT,
                "use_proxy": False,
            },
            enable_entrypoint=True,
            can_complete_tasks=True,
            tool_format="completions",
        )

        return MAILSwarmTemplate(
            name="task_summarizer",
            version="1.0.0",
            agents=[agent],
            actions=[submit_title_action],
            entrypoint="summarizer",
            breakpoint_tools=["submit_title"],
            exclude_tools=["task_complete"],  # Force use of submit_title breakpoint
        )

    async def _get_swarm(self) -> "MAILSwarm":
        """Get or create the swarm instance."""
        if self._swarm is None:
            self._swarm = self._template.instantiate(
                instance_params={"user_token": "summarizer"},
                user_id="summarizer_user",
            )
        return self._swarm

    def _parse_title(self, response: dict) -> str | None:
        """Parse the title from the breakpoint tool call response."""
        message = response.get("message", {})
        subject = message.get("subject", "")
        body = message.get("body", "")

        if subject != "::breakpoint_tool_call::" or not body:
            return None

        try:
            body_data = json.loads(body)

            # Tool calls are standardized to OpenAI/LiteLLM format:
            # [{"arguments": "{\"title\":\"...\"}", "name": "submit_title", "id": "..."}]
            if isinstance(body_data, list):
                for call in body_data:
                    if call.get("name") == "submit_title":
                        args = call.get("arguments", "{}")
                        if isinstance(args, str):
                            args = json.loads(args)
                        return args.get("title")

            return None
        except (json.JSONDecodeError, KeyError, TypeError):
            return None

    async def summarize(
        self,
        messages: list[dict],
        max_messages: int = 10,
    ) -> str | None:
        """
        Generate a title for a conversation.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
                     Only 'user' and 'assistant' roles are included.
            max_messages: Maximum number of recent messages to include (default 10)

        Returns:
            A short title string, or None if generation failed.
        """
        # Filter to user/assistant messages and take last N
        filtered = [
            m for m in messages
            if m.get("role") in ("user", "assistant")
        ][-max_messages:]

        if not filtered:
            return None

        # Format messages for the prompt
        formatted = []
        for msg in filtered:
            role = msg["role"].upper()
            content = msg.get("content", "")
            # Truncate long messages
            if len(content) > 500:
                content = content[:500] + "..."
            formatted.append(f"{role}: {content}")

        prompt = "Generate a title for this conversation:\n\n" + "\n\n".join(formatted)

        swarm = await self._get_swarm()

        response, _ = await swarm.post_message_and_run(
            body=prompt,
            subject="Summarize",
            show_events=False,
        )

        return self._parse_title(response) # type: ignore

    async def shutdown(self):
        """Shutdown the swarm."""
        if self._swarm is not None:
            await self._swarm.shutdown()
            self._swarm = None


async def summarize_task(messages: list[dict], max_messages: int = 10) -> str | None:
    """
    Generate a title for a conversation.

    Creates a fresh swarm per request to avoid concurrency issues.

    Args:
        messages: List of message dicts with 'role' and 'content' keys
        max_messages: Maximum recent messages to include

    Returns:
        A short title string, or None if generation failed
    """
    summarizer = TaskSummarizer()
    try:
        return await summarizer.summarize(messages, max_messages)
    finally:
        await summarizer.shutdown()
