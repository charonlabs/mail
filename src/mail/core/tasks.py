# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import datetime
from typing import Literal, cast

from sse_starlette import ServerSentEvent

from mail.core.message import MAILMessage, create_agent_address


class MAILTask:
    """
    A discrete collection of messages between agents working towards a common goal.
    """

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.start_time = datetime.datetime.now(datetime.UTC)
        self.events: list[ServerSentEvent] = []
    
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
            sent_messages = [message for message in self.get_messages() if message["message"]["sender"] == agent_address]
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
        message_type: Literal["request", "response", "broadcast", "interrupt", "broadcast_complete"]
    ) -> list[MAILMessage]:
        """
        Get all messages of a given type.
        """
        return [message for message in self.get_messages() if message["msg_type"] == message_type]

    def get_messages_by_system(self) -> list[MAILMessage]:
        """
        Get all messages from the system.
        """
        return [message for message in self.get_messages() if message["message"]["sender"]["address_type"] == "system"]

    def get_messages_by_user(self) -> list[MAILMessage]:
        """
        Get all messages from the user.
        """
        return [message for message in self.get_messages() if message["message"]["sender"]["address_type"] == "user"]

    def get_lifetime(self) -> datetime.timedelta:
        """
        Get the lifetime of the task.
        """
        return datetime.datetime.now(datetime.UTC) - self.start_time