# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import datetime
import heapq
from asyncio import PriorityQueue
from typing import Literal, cast

import ujson
from sse_starlette import ServerSentEvent

from mail.core.message import MAILMessage, create_agent_address

QueueItem = tuple[int, int, MAILMessage]


class MAILTask:
    """
    A discrete collection of messages between agents working towards a common goal.
    """

    def __init__(
        self,
        task_id: str,
        task_owner: str,
        task_contributors: list[str],
    ) -> None:
        self.task_id = task_id
        self.task_owner = task_owner
        self.task_contributors = task_contributors
        self.start_time = datetime.datetime.now(datetime.UTC)
        self.events: list[ServerSentEvent] = []
        self.is_running = False
        self.task_message_queue: list[QueueItem] = []
        self.remote_swarms: set[str] = set()
        self.completed = False
        # Title for UI task history (generated once via Haiku)
        self.title: str | None = None

    def add_event(self, event: ServerSentEvent) -> None:
        """
        Add a new event to the task.
        """
        self.events.append(event)

    def get_messages(self) -> list[MAILMessage]:
        """
        Get all messages for the task.
        """
        messages: list[MAILMessage] = []

        for sse in self.events:
            if sse.event == "new_message":
                data = sse.data
                if data is None:
                    continue
                if isinstance(data, str):
                    try:
                        data = ujson.loads(data)
                    except ValueError:
                        continue
                if not isinstance(data, dict):
                    continue
                extra_data = data.get("extra_data")
                if extra_data is None:
                    continue
                full_message = extra_data.get("full_message")
                if full_message is None:
                    continue

                messages.append(cast(MAILMessage, full_message))

        return messages

    def get_messages_by_agent(
        self,
        agent: str,
        sent: bool = True,
        received: bool = True,
    ) -> list[MAILMessage]:
        """
        Get all messages for a given agent (whether sent or received).
        """
        agent_address = create_agent_address(agent)

        sent_messages: list[MAILMessage] = []
        if sent:
            sent_messages = [
                message
                for message in self.get_messages()
                if message["message"]["sender"] == agent_address
            ]
        received_messages: list[MAILMessage] = []
        if received:
            for message in self.get_messages():
                match message["msg_type"]:
                    case "request" | "response":
                        if message["message"]["recipient"] == agent_address:  # type: ignore
                            received_messages.append(message)
                    case "broadcast" | "interrupt" | "broadcast_complete":
                        if agent_address in message["message"]["recipients"]:  # type: ignore
                            received_messages.append(message)
                    case _:
                        raise ValueError(f"invalid message type: {message['msg_type']}")

        return sent_messages + received_messages

    def get_messages_by_type(
        self,
        message_type: Literal[
            "request", "response", "broadcast", "interrupt", "broadcast_complete"
        ],
    ) -> list[MAILMessage]:
        """
        Get all messages of a given type.
        """
        return [
            message
            for message in self.get_messages()
            if message["msg_type"] == message_type
        ]

    def get_messages_by_system(self) -> list[MAILMessage]:
        """
        Get all messages from the system.
        """
        return [
            message
            for message in self.get_messages()
            if message["message"]["sender"]["address_type"] == "system"
        ]

    def get_messages_by_user(self) -> list[MAILMessage]:
        """
        Get all messages from the user.
        """
        return [
            message
            for message in self.get_messages()
            if message["message"]["sender"]["address_type"] == "user"
        ]

    def get_lifetime(self) -> datetime.timedelta:
        """
        Get the lifetime of the task.
        """
        return datetime.datetime.now(datetime.UTC) - self.start_time

    async def queue_stash(
        self,
        message_queue: PriorityQueue[QueueItem],
    ) -> None:
        """
        Remove any queued messages for this task from the shared runtime queue and
        store them for later restoration when the task resumes.
        """
        try:
            raw_queue = list(getattr(message_queue, "_queue", []))
        except Exception:
            raw_queue = []

        if not raw_queue:
            self.task_message_queue = []
            return

        remaining: list[QueueItem] = []
        stashed: list[QueueItem] = []

        for item in raw_queue:
            try:
                queued_task_id = item[2]["message"]["task_id"]
            except Exception:
                remaining.append(item)
                continue

            if queued_task_id == self.task_id:
                stashed.append(item)
            else:
                remaining.append(item)

        if not stashed:
            self.task_message_queue = []
            return

        try:
            message_queue._queue.clear()  # type: ignore[attr-defined]
            message_queue._queue.extend(remaining)  # type: ignore[attr-defined]
            heapq.heapify(message_queue._queue)  # type: ignore[attr-defined]
        except Exception:
            # If direct manipulation fails, reassigning the queue isn't critical;
            # continue with captured snapshot to avoid losing the task state.
            pass

        unfinished = getattr(message_queue, "_unfinished_tasks", None)
        if isinstance(unfinished, int):
            message_queue._unfinished_tasks = max(0, unfinished - len(stashed))  # type: ignore[attr-defined]

        self.task_message_queue = stashed

    async def queue_load(
        self,
        message_queue: PriorityQueue[QueueItem],
    ) -> None:
        """
        Restore any previously stashed messages for this task back into the shared
        runtime queue.
        """
        if not self.task_message_queue:
            return

        stashed = list(self.task_message_queue)

        try:
            message_queue._queue.extend(stashed)  # type: ignore[attr-defined]
            heapq.heapify(message_queue._queue)  # type: ignore[attr-defined]
        except Exception:
            # If we cannot directly restore to the shared queue, keep the snapshot
            # so that a future attempt can retry.
            return

        unfinished = getattr(message_queue, "_unfinished_tasks", None)
        if isinstance(unfinished, int):
            message_queue._unfinished_tasks = unfinished + len(stashed)  # type: ignore[attr-defined]

        self.task_message_queue = []
        self.completed = False

    def mark_complete(self) -> None:
        """
        Mark the task as complete and stop active processing.
        """
        self.completed = True
        self.is_running = False

    def resume(self) -> None:
        """
        Mark the completed task as running again.
        """
        self.completed = False
        self.is_running = True

    def add_remote_swarm(self, remote_swarm: str) -> None:
        """
        Track a remote swarm participating in this task.
        """
        self.remote_swarms.add(remote_swarm)

    def to_db_dict(self) -> dict:
        """
        Serialize the task to a dictionary for database storage.
        Does not include events (stored separately) or task_message_queue (not persisted).
        """
        return {
            "task_id": self.task_id,
            "task_owner": self.task_owner,
            "task_contributors": self.task_contributors,
            "remote_swarms": list(self.remote_swarms),
            "is_running": self.is_running,
            "completed": self.completed,
            "start_time": self.start_time.isoformat(),
            "title": self.title,
        }

    @classmethod
    def from_db_dict(cls, data: dict) -> "MAILTask":
        """
        Create a MAILTask from a database record dictionary.
        """
        task = cls(
            task_id=data["task_id"],
            task_owner=data["task_owner"],
            task_contributors=data.get("task_contributors", []),
        )
        # Restore state from DB
        task.is_running = data.get("is_running", False)
        task.completed = data.get("completed", False)
        task.remote_swarms = set(data.get("remote_swarms", []))

        # Parse start_time if it's a string
        start_time = data.get("start_time")
        if start_time:
            if isinstance(start_time, str):
                task.start_time = datetime.datetime.fromisoformat(start_time)
            elif isinstance(start_time, datetime.datetime):
                task.start_time = start_time

        # Restore title
        task.title = data.get("title")

        return task

    def add_event_from_db(self, event_data: dict) -> None:
        """
        Add an event from a database record.
        """
        import json

        # Parse event data if it's a JSON string
        data = event_data.get("data")
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                pass  # Keep as string if not valid JSON

        event = ServerSentEvent(
            event=event_data.get("event"),
            data=data,
            id=event_data.get("id"),
        )
        self.events.append(event)
