import asyncio
from datetime import datetime
from typing import Any
import uuid

from openai.types.responses import (
    Response,
    ResponseInputItem,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseFunctionToolCall,
)
import ujson

from mail.api import MAILSwarmTemplate, MAILSwarm, MAILAction
from mail.utils.serialize import dump_mail_result


async def async_lambda(x: Any) -> Any:
    return x


class SwarmOAIClient:
    def __init__(
        self,
        template: MAILSwarmTemplate,
    ):
        self.responses = self.Responses(self)
        self.template = template
        self.result_dumps: dict[str, list[Any]] = {}
        self.swarm: MAILSwarm | None = None

    class Responses:
        def __init__(self, owner: "SwarmOAIClient"):
            self.owner = owner

        async def create(
            self,
            input: list[ResponseInputItem],
            tools: list[dict[str, Any]],
            instructions: str | None = None,
            previous_response_id: str | None = None,
            tool_choice: str | dict[str, str] = "auto",
            parallel_tool_calls: bool = True,
            **kwargs: Any,
        ) -> Response:
            if self.owner.swarm is None:
                new_swarm = self.owner.template
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
                    complete_agent = next(
                        (a for a in new_swarm.agents if a.can_complete_tasks), None
                    )
                    assert complete_agent is not None
                    complete_agent.actions += new_actions
                    if instructions is not None:
                        raw_sys_msg = {"content": instructions}
                    else:
                        raw_sys_msg = next(
                            msg
                            for msg in kwargs["messages"]
                            if (msg["role"] == "system" or msg["role"] == "developer")
                        )
                    complete_agent.agent_params["system"] = (
                        complete_agent.agent_params["system"]
                        + raw_sys_msg["content"]
                        + f"\n\nYou can perform actions in the environment by calling one of the following tools: {', '.join([a.name for a in new_actions])}"
                    )
                new_swarm.breakpoint_tools = [a.name for a in new_actions]
                self.owner.swarm = new_swarm.instantiate({"user_token": ""})
                asyncio.create_task(self.owner.swarm.run_continuous())
            swarm = self.owner.swarm
            body = ""
            if input[-1].type == "function_call_output":
                tool_responses: list[dict[str, Any]] = []
                for input_item in reversed(input):
                    if input_item.type == "function_call":
                        break
                    if input_item.type == "function_call_output":
                        tool_responses.append(
                            {
                                "call_id": input_item.call_id,
                                "content": input_item.output,
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
                    if (
                        not input_item.type == "message"
                        or not input_item.role == "user"
                    ):
                        break
                    body = (
                        f"<environment>\n{input_item.content}\n</environment>\n\n{body}"
                    )
                out, events = await swarm.post_message(
                    body=body,
                    subject="Task Request",
                    task_id=str(id),
                    show_events=True,
                )
            response_id = out["message"]["task_id"]
            dump = dump_mail_result(result=out, events=events, verbose=True)
            self.owner.result_dumps[response_id].append(dump)
            has_called_tools = out["message"]["subject"] == "::breakpoint_tool_call::"
            if not has_called_tools:
                return Response(
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
            tool_calls: list[ResponseFunctionToolCall] = []
            body = ujson.loads(out["message"]["body"])
            print(f"=== Body ===\n{body}\n=== ===")
            for tool_call in body:
                tool_calls.append(
                    ResponseFunctionToolCall(
                        call_id=tool_call["call_id"],
                        name=tool_call["name"],
                        arguments=ujson.dumps(tool_call["arguments"]),
                        type="function_call",
                        id=tool_call["id"],
                        status=tool_call["status"],
                    )
                )
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
