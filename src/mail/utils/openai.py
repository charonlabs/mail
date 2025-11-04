import asyncio
import uuid
from datetime import datetime
from typing import Any

import ujson
from openai.types.responses import (
    Response,
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)
from pydantic import BaseModel, ValidationError

from mail.api import MAILAction, MAILSwarm, MAILSwarmTemplate
from mail.utils.serialize import dump_mail_result


async def async_lambda(x: Any) -> Any:
    return x


def build_oai_clients_dict() -> dict[str, "SwarmOAIClient"]:
    """
    Build a dictionary of SwarmOAIClient instances for each API key in the environment.
    """
    return {}


class SwarmOAIClient:
    def __init__(
        self,
        template: MAILSwarmTemplate,
        instance: MAILSwarm | None = None,
        validate_responses: bool = True,
    ):
        self.responses = self.Responses(self)
        self.template = template
        self.result_dumps: dict[str, list[Any]] = {}
        self.swarm = instance
        self.validate_responses = validate_responses

    class Responses:
        def __init__(self, owner: "SwarmOAIClient"):
            self.owner = owner

        async def create(
            self,
            input: list[dict[str, Any]],
            tools: list[dict[str, Any]],
            instructions: str | None = None,
            previous_response_id: str | None = None,
            tool_choice: str | dict[str, str] = "auto",
            parallel_tool_calls: bool = True,
            api_key: str | None = None,
            **kwargs: Any,
        ) -> Response:
            if self.owner.swarm is None:
                new_swarm = self.owner.template
                complete_agent = next(
                    (a for a in new_swarm.agents if a.can_complete_tasks), None
                )
                assert complete_agent is not None
                if instructions is not None:
                    raw_sys_msg = {"content": instructions}
                else:
                    raw_sys_msg = next(
                        (
                            input_item  # type: ignore
                            for input_item in input
                            if (
                                "role" in input_item
                                and input_item["role"] == "system"
                                or input_item["role"] == "developer"
                            )
                        ),
                        {"content": ""},
                    )
                complete_agent.agent_params["system"] = (
                    complete_agent.agent_params["system"] + raw_sys_msg["content"]
                )
                if len(tools) > 0:
                    new_actions: list[MAILAction] = []
                    for tool in tools:
                        name = tool["name"]
                        description = tool["description"]
                        parameters = tool["parameters"]
                        new_actions.append(
                            MAILAction(
                                name=name,
                                description=description,
                                parameters=parameters,
                                function=async_lambda,
                            )
                        )
                        complete_agent.actions += new_actions
                        new_swarm.actions += new_actions
                        complete_agent.agent_params["system"] = (
                            complete_agent.agent_params["system"]
                            + f"\n\nYou can perform actions in the environment by calling one of the following tools: {', '.join([a.name for a in new_actions])}"
                        )
                        new_swarm.breakpoint_tools = [a.name for a in new_actions]

                self.owner.swarm = new_swarm.instantiate({"user_token": ""})
                asyncio.create_task(self.owner.swarm.run_continuous())
            swarm = self.owner.swarm
            body = ""
            if "type" in input[-1] and input[-1]["type"] == "function_call_output":
                tool_responses: list[dict[str, Any]] = []
                for input_item in reversed(input):
                    if (
                        "type" not in input_item
                        or input_item["type"] == "function_call"
                    ):
                        break
                    if input_item["type"] == "function_call_output":
                        tool_responses.append(
                            {
                                "call_id": input_item["call_id"],
                                "content": input_item["output"],
                            }
                        )
                out, events = await swarm.post_message(
                    body="",
                    subject="Tool Response",
                    task_id=previous_response_id,
                    show_events=True,
                    resume_from="breakpoint_tool_call",
                    breakpoint_tool_call_result=tool_responses,
                )
            else:
                for input_item in reversed(input):
                    if isinstance(input_item, BaseModel):
                        input_item = input_item.model_dump()
                    if (
                        ("role" in input_item and input_item["role"] == "assistant")
                        or "type" in input_item
                        and (
                            input_item["type"]
                            in ["function_call_output", "function_call"]
                        )
                    ):
                        break
                    body = f"{input_item['content']}\n\n{body}"
                out, events = await swarm.post_message(
                    body=body,
                    subject="Task Request",
                    task_id=previous_response_id,
                    show_events=True,
                )
            response_id = out["message"]["task_id"]
            dump = dump_mail_result(result=out, events=events, verbose=True)
            if response_id not in self.owner.result_dumps:
                self.owner.result_dumps[response_id] = []
            self.owner.result_dumps[response_id].append(dump)
            has_called_tools = out["message"]["subject"] == "::breakpoint_tool_call::"
            if not has_called_tools:
                response = Response(
                    id=response_id,
                    created_at=float(datetime.now().timestamp()),
                    model=f"{swarm.name}",
                    object="response",
                    tools=tools,  # type: ignore
                    output=[
                        ResponseOutputMessage(
                            type="message",
                            id=str(uuid.uuid4()),
                            status="completed",
                            role="assistant",
                            content=[
                                ResponseOutputText(
                                    type="output_text",
                                    text=out["message"]["body"],
                                    annotations=[],
                                )
                            ],
                        )
                    ],
                    parallel_tool_calls=parallel_tool_calls,
                    tool_choice=tool_choice,  # type: ignore
                )
                return response

            tool_calls: list[ResponseFunctionToolCall] = []
            body = ujson.loads(out["message"]["body"])
            for tool_call in body:
                tool_calls.append(
                    ResponseFunctionToolCall(
                        call_id=tool_call["call_id"],
                        name=tool_call["name"],
                        arguments=tool_call["arguments"],
                        type="function_call",
                        id=tool_call["id"],
                        status=tool_call["status"],
                    )
                )
            try:
                return Response(
                    id=response_id,
                    created_at=float(datetime.now().timestamp()),
                    model=f"{swarm.name}",
                    object="response",
                    tools=tools,  # type: ignore
                    output=tool_calls,  # type: ignore
                    parallel_tool_calls=parallel_tool_calls,
                    tool_choice=tool_choice,  # type: ignore
                )
            except ValidationError as e:
                if self.owner.validate_responses:
                    raise e
                else:
                    return response
