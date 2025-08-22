# FastAPI server for MAIL over HTTP

import datetime
import logging
import uuid
import asyncio
import os
from contextlib import asynccontextmanager
from typing import Dict, Optional

import uvicorn
import aiohttp
from fastapi import FastAPI, HTTPException, Request, Depends
from toml import load as load_toml

from .core import MAIL
from .message import (
    MAILMessage,
    MAILRequest,
    MAILInterswarmMessage,
    MAILResponse,
    create_user_address,
    create_agent_address,
    format_agent_address,
)
from .logger import init_logger
from .swarms.builder import build_swarm_from_name, build_swarm_from_json_str
from .auth import generate_agent_id, generate_user_id, login, get_token_info
from .swarm_registry import SwarmRegistry


# Initialize logger at module level so it runs regardless of how the server is started
init_logger()
logger = logging.getLogger("mail")

# Global variables
persistent_swarm = None
user_mail_instances: Dict[str, MAIL] = {}
user_mail_tasks: Dict[str, asyncio.Task] = {}
swarm_mail_instances: Dict[str, MAIL] = {}
swarm_mail_tasks: Dict[str, asyncio.Task] = {}

# Interswarm messaging support
swarm_registry: Optional[SwarmRegistry] = None
local_swarm_name: str = "example"
local_base_url: str = "http://localhost:8000"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    # Startup
    logger.info("MAIL server starting up...")

    # Initialize swarm registry for interswarm messaging
    global swarm_registry, local_swarm_name, local_base_url

    # Get configuration from environment
    local_swarm_name = os.getenv("SWARM_NAME", "example")
    local_base_url = os.getenv("BASE_URL", "http://localhost:8000")
    persistence_file = os.getenv("SWARM_REGISTRY_FILE", "registries/example.json")

    swarm_registry = SwarmRegistry(local_swarm_name, local_base_url, persistence_file)

    # Start health checks
    await swarm_registry.start_health_checks()

    # Create persistent swarm at startup
    global persistent_swarm
    try:
        logger.info("building persistent swarm...")
        persistent_swarm = build_swarm_from_name(local_swarm_name)
        logger.info("persistent swarm built successfully")
    except Exception as e:
        logger.error(f"error building persistent swarm: '{e}'")
        raise e

    yield

    # Shutdown
    logger.info("MAIL server shutting down...")

    # Stop swarm registry and cleanup volatile endpoints
    if swarm_registry:
        await swarm_registry.stop_health_checks()
        # Clean up volatile endpoints and save persistent ones
        swarm_registry.cleanup_volatile_endpoints()

    # Clean up all user MAIL instances
    global user_mail_instances, user_mail_tasks
    for user_id, mail_instance in user_mail_instances.items():
        logger.info(f"shutting down MAIL instance for user: '{user_id}'...")
        await mail_instance.shutdown()

    for user_id, mail_task in user_mail_tasks.items():
        if mail_task and not mail_task.done():
            logger.info(f"cancelling MAIL task for user: '{user_id}'...")
            mail_task.cancel()
            try:
                await mail_task
            except asyncio.CancelledError:
                pass

    # Clean up all swarm MAIL instances
    global swarm_mail_instances, swarm_mail_tasks
    for swarm_id, mail_instance in swarm_mail_instances.items():
        logger.info(f"shutting down MAIL instance for swarm: '{swarm_id}'...")
        await mail_instance.shutdown()

    for swarm_id, mail_task in swarm_mail_tasks.items():
        if mail_task and not mail_task.done():
            logger.info(f"cancelling MAIL task for swarm: '{swarm_id}'...")
            mail_task.cancel()
            try:
                await mail_task
            except asyncio.CancelledError:
                pass


app = FastAPI(lifespan=lifespan)


async def get_or_create_user_mail(user_id: str, jwt: str) -> MAIL:
    """
    Get or create a MAIL instance for a specific user.
    Each user gets their own isolated MAIL instance.
    """
    global persistent_swarm, user_mail_instances, user_mail_tasks, swarm_registry

    if user_id not in user_mail_instances:
        try:
            logger.info(f"creating MAIL instance for user: '{user_id}'...")

            # Create a new MAIL instance for this user with interswarm support
            mail_instance = persistent_swarm.instantiate(
                user_id=user_id,
                user_token=jwt,
                swarm_name=local_swarm_name,
                swarm_registry=swarm_registry,
                enable_interswarm=True,
            )
            user_mail_instances[user_id] = mail_instance

            # Start interswarm messaging
            await mail_instance.start_interswarm()

            # Start the MAIL instance in continuous mode for this user
            logger.info(f"starting MAIL continuous mode for user: '{user_id}'...")
            mail_task = asyncio.create_task(mail_instance.run_continuous())
            user_mail_tasks[user_id] = mail_task

            logger.info(f"MAIL instance created and started for user: '{user_id}'")

        except Exception as e:
            logger.error(
                f"error creating MAIL instance for user '{user_id}' with error: '{e}'"
            )
            raise e

    return user_mail_instances[user_id]


async def get_or_create_swarm_mail(swarm_id: str, jwt: str) -> MAIL:
    """
    Get or create a MAIL instance for a specific swarm.
    Each swarm gets their own isolated MAIL instance.
    """
    global persistent_swarm, swarm_mail_instances, swarm_mail_tasks, swarm_registry

    if swarm_id not in swarm_mail_instances:
        try:
            logger.info(f"creating MAIL instance for swarm: '{swarm_id}'...")

            # Create a new MAIL instance for this user with interswarm support
            mail_instance = persistent_swarm.instantiate(
                user_id=swarm_id,
                user_token=jwt,
                swarm_name=local_swarm_name,
                swarm_registry=swarm_registry,
                enable_interswarm=True,
            )
            swarm_mail_instances[swarm_id] = mail_instance

            # Start interswarm messaging
            await mail_instance.start_interswarm()

            # Start the MAIL instance in continuous mode for this user
            logger.info(f"starting MAIL continuous mode for swarm: '{swarm_id}'...")
            mail_task = asyncio.create_task(mail_instance.run_continuous())
            swarm_mail_tasks[swarm_id] = mail_task

            logger.info(f"MAIL instance created and started for swarm: '{swarm_id}'")

        except Exception as e:
            logger.error(
                f"error creating MAIL instance for swarm '{swarm_id}' with error: '{e}'"
            )
            raise e

    return swarm_mail_instances[swarm_id]


@app.get("/")
async def root():
    logger.info("root endpoint accessed")
    version = load_toml("pyproject.toml")["project"]["version"]
    return {"name": "mail", "status": "ok", "version": version}


@app.get("/status")
async def status(request: Request):
    """Get the status of the persistent swarm and user-specific MAIL instances."""
    global persistent_swarm, user_mail_instances, user_mail_tasks

    # Get user token from request
    api_key = request.headers.get("Authorization")
    if api_key and api_key.startswith("Bearer "):
        jwt = await login(api_key.split(" ")[1])
        token_info = await get_token_info(jwt)
        user_id = generate_user_id(token_info)

        user_mail_status = user_id in user_mail_instances
        user_task_running = (
            user_id in user_mail_tasks and not user_mail_tasks[user_id].done()
            if user_id in user_mail_tasks
            else False
        )
    else:
        user_mail_status = False
        user_task_running = False

    return {
        "swarm": {
            "name": persistent_swarm.name if persistent_swarm else None,
            "status": "ready",
        },
        "active_users": len(user_mail_instances),
        "user_mail_ready": user_mail_status,
        "user_task_running": user_task_running,
    }


@app.post("/chat")
async def chat(request: Request):
    """
    Handle chat requests from the client.
    Uses a user-specific MAIL instance to process the request and returns the response.

    Args:
        request: The request object containing the chat message.

    Returns:
        A dictionary containing the response message.
    """
    logger.info("chat endpoint accessed")

    # auth process
    api_key = request.headers.get("Authorization")
    if api_key is None:
        logger.warning("no API key provided")
        raise HTTPException(status_code=401, detail="no API key provided")

    if api_key.startswith("Bearer "):
        jwt = await login(api_key.split(" ")[1])
        logger.info(f"user authenticated with token: '{jwt[:8]}...'...")
    else:
        logger.warning("invalid API key format")
        raise HTTPException(status_code=401, detail="invalid API key format")

    token_info = await get_token_info(jwt)
    role = token_info["role"]
    if (role != "user") and (role != "admin"):
        logger.warning("invalid role")
        raise HTTPException(status_code=401, detail="invalid role")
    user_id = generate_user_id(token_info)

    # Get or create user-specific MAIL instance
    try:
        user_mail = await get_or_create_user_mail(user_id, jwt)
    except Exception as e:
        logger.error(f"error getting user MAIL instance: '{e}'")
        raise HTTPException(
            status_code=500,
            detail=f"error getting user MAIL instance: {e.with_traceback(None)}",
        )

    # parse request
    try:
        data = await request.json()
        message = data.get("message", "")
        logger.info(f"received message from user '{user_id}': '{message[:50]}...'")
    except Exception as e:
        logger.error(f"error parsing request: '{e}'")
        raise HTTPException(
            status_code=400, detail=f"error parsing request: {e.with_traceback(None)}"
        )

    if not message:
        logger.warning("no message provided")
        raise HTTPException(status_code=400, detail="no message provided")

    # MAIL process
    try:
        logger.info(f"creating MAIL message for user '{user_id}'...")
        new_message = MAILMessage(
            id=str(uuid.uuid4()),
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            message=MAILRequest(
                task_id=str(uuid.uuid4()),
                request_id=str(uuid.uuid4()),
                sender=create_user_address(user_id),
                recipient=create_agent_address("supervisor"),
                subject="New Message",
                body=message,
            ),
            msg_type="request",
        )
        logger.info(f"submitting message to user MAIL and waiting for response...")
        response = await user_mail.submit_and_wait(new_message)
        logger.info(f"MAIL completed successfully for user '{user_id}'")
        return {"response": response["message"]["body"]}
    except Exception as e:
        logger.error(f"error processing message for user '{user_id}' with error: '{e}'")
        raise HTTPException(
            status_code=500,
            detail=f"error processing message: {e.with_traceback(None)}",
        )


@app.get("/health")
async def health():
    """Health check endpoint for interswarm communication."""
    return {
        "status": "healthy",
        "swarm_name": local_swarm_name,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


@app.get("/swarms")
async def list_swarms():
    """List all known swarms for service discovery."""
    global swarm_registry
    if not swarm_registry:
        raise HTTPException(status_code=503, detail="swarm registry not available")

    endpoints = swarm_registry.get_all_endpoints()
    swarms = []

    for name, endpoint in endpoints.items():
        swarms.append(
            {
                "name": endpoint["swarm_name"],
                "base_url": endpoint["base_url"],
                "is_active": endpoint["is_active"],
                "last_seen": endpoint["last_seen"].isoformat()
                if endpoint["last_seen"]
                else None,
                "metadata": endpoint["metadata"],
            }
        )

    return {"swarms": swarms}


@app.post("/swarms/register")
async def register_swarm(request: Request):
    """
    Register a new swarm in the registry.
    Only admins can register new swarms.
    If "volatile" is False, the swarm will be persistent and will not be removed from the registry when the server shuts down.
    """
    global swarm_registry
    if not swarm_registry:
        raise HTTPException(status_code=503, detail="swarm registry not available")

    try:
        # auth process
        api_key = request.headers.get("Authorization")
        if api_key is None:
            logger.warning("no API key provided")
            raise HTTPException(status_code=401, detail="no API key provided")

        if api_key.startswith("Bearer "):
            jwt = await login(api_key.split(" ")[1])
            logger.info(f"swarm registered with token: '{jwt[:8]}...'...")
        else:
            logger.warning("invalid API key format")
            raise HTTPException(status_code=401, detail="invalid API key format")

        token_info = await get_token_info(jwt)
        role = token_info["role"]
        if role != "admin":
            logger.warning("invalid role")
            raise HTTPException(status_code=401, detail="invalid role")

        # parse request
        data = await request.json()
        swarm_name = data.get("name")
        base_url = data.get("base_url")
        auth_token = data.get("auth_token")
        volatile = data.get("volatile", True)
        metadata = data.get("metadata")

        if not swarm_name or not base_url:
            raise HTTPException(
                status_code=400, detail="name and base_url are required"
            )

        swarm_registry.register_swarm(
            swarm_name, base_url, auth_token, metadata, volatile
        )
        return {"status": "registered", "swarm_name": swarm_name}

    except Exception as e:
        logger.error(f"error registering swarm: '{e}'")
        raise HTTPException(
            status_code=500, detail=f"error registering swarm: '{str(e)}'"
        )

@app.get("/swarms/dump")
async def dump_swarm(request: Request):
    global persistent_swarm

    logger.info("dump swarm endpoint accessed")

    # auth
    api_key = request.headers.get("Authorization")
    if api_key is None:
        logger.warning("no API key provided")
        raise HTTPException(status_code=401, detail="no API key provided")
    
    if api_key.startswith("Bearer "):
        jwt = await login(api_key.split(" ")[1])
        logger.info("successfully authenticated")
    else:
        logger.warning("invalid API key format")
        raise HTTPException(status_code=401, detail="invalid API key format")
    
    # make sure the endpoint was hit by an admin
    token_info = await get_token_info(jwt)
    role = token_info["role"]
    if role != "admin":
        logger.warning("invalid role for dumping swarm")
        raise HTTPException(status_code=401, detail="invalid role for dumping swarm")
    
    # log da swarm
    logger.info(f"current persistent swarm: name='{persistent_swarm.name}', agents={[agent.name for agent in persistent_swarm.agents]}")

    # all done!
    return {"status": "dumped", "swarm_name": persistent_swarm.name}

@app.post("/interswarm/message")
async def receive_interswarm_message(request: Request):
    """Receive an interswarm message from another swarm."""
    logger.info("interswarm message endpoint accessed")

    # auth process
    api_key = request.headers.get("Authorization")
    if api_key is None:
        logger.warning("no API key provided")
        raise HTTPException(status_code=401, detail="no API key provided")

    if api_key.startswith("Bearer "):
        jwt = await login(api_key.split(" ")[1])
        logger.info(f"agent authenticated with token: '{jwt[:8]}...'...")
    else:
        logger.warning("invalid API key format")
        raise HTTPException(status_code=401, detail="invalid API key format")

    token_info = await get_token_info(jwt)
    role = token_info["role"]
    if role != "agent":
        logger.warning("invalid role")
        raise HTTPException(status_code=401, detail="invalid role")
    swarm_id = generate_agent_id(token_info)

    # Get or create swarm-specific MAIL instance
    try:
        swarm_mail = await get_or_create_swarm_mail(swarm_id, jwt)
    except Exception as e:
        logger.error(f"error getting swarm MAIL instance: '{e}'")
        raise HTTPException(
            status_code=500,
            detail=f"error getting swarm MAIL instance: {e.with_traceback(None)}",
        )

    # parse request
    try:
        data = await request.json()
        interswarm_message = MAILInterswarmMessage(**data)
        message = interswarm_message["payload"]
        source_swarm = interswarm_message["source_swarm"]
        source_agent = message.get("sender", {})
        target_agent = message.get("recipient", {})

        logger.info(
            f"Received message from {source_agent} to {target_agent}: {message.get('subject', 'unknown')}..."
        )
    except Exception as e:
        logger.error(f"error parsing request: '{e}'")
        raise HTTPException(
            status_code=400, detail=f"error parsing request: {e.with_traceback(None)}"
        )

    if not message:
        logger.warning("no message provided")
        raise HTTPException(status_code=400, detail="no message provided")

    # MAIL process
    try:
        logger.info(f"creating MAIL message for swarm '{source_swarm}'...")
        new_message = MAILMessage(
            id=str(uuid.uuid4()),
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            message=message,
            msg_type=data.get("msg_type", "request"),
        )
        logger.info(
            f"submitting message '{new_message['id']}' to agent MAIL and waiting for response..."
        )
        task_response = await swarm_mail.submit_and_wait(new_message)

        # Create response message
        response_message = MAILMessage(
            id=str(uuid.uuid4()),
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            message=MAILResponse(
                task_id=task_response["message"]["task_id"],
                request_id=task_response["message"].get(
                    "request_id", task_response["message"]["task_id"]
                ),
                sender=task_response["message"]["sender"],
                recipient=source_agent,
                subject=task_response["message"]["subject"],
                body=task_response["message"]["body"],
                sender_swarm=local_swarm_name,
                recipient_swarm=source_swarm,
            ),
            msg_type="response",
        )

        # Send response back to the source swarm via HTTP
        await _send_response_to_swarm(source_swarm, response_message)

        logger.info(
            f"MAIL completed successfully for swarm '{source_swarm}' with response '{response_message}'"
        )
        return response_message

    except Exception as e:
        logger.error(
            f"error processing message for swarm '{source_swarm}' with response '{response_message}' with error: '{e}'"
        )
        raise HTTPException(
            status_code=500,
            detail=f"error processing message: {e.with_traceback(None)}",
        )


@app.post("/interswarm/response")
async def receive_interswarm_response(request: Request):
    """Receive an interswarm response from another swarm."""
    logger.info("interswarm response endpoint accessed")

    # auth process
    api_key = request.headers.get("Authorization")
    if api_key is None:
        logger.warning("no API key provided")
        raise HTTPException(status_code=401, detail="no API key provided")

    if api_key.startswith("Bearer "):
        jwt = await login(api_key.split(" ")[1])
        logger.info(f"response received with token: '{jwt[:8]}...'...")
    else:
        logger.warning("invalid API key format")
        raise HTTPException(status_code=401, detail="invalid API key format")

    token_info = await get_token_info(jwt)
    role = token_info["role"]
    if role != "agent":
        logger.warning("invalid role")
        raise HTTPException(status_code=401, detail="invalid role")

    # parse request
    try:
        data = await request.json()
        response_message = MAILMessage(**data)
        logger.info(
            f"received response from '{response_message['message']['sender']}': '{response_message['message']['subject']}'..."
        )
    except Exception as e:
        logger.error(f"error parsing response: '{e}'")
        raise HTTPException(
            status_code=400, detail=f"error parsing response: {e.with_traceback(None)}"
        )

    # Find the appropriate MAIL instance to handle this response
    # We need to match it based on the task_id or request_id
    global user_mail_instances, swarm_mail_instances

    # Try to find the MAIL instance that sent the original request
    task_id = response_message["message"]["task_id"]
    request_id = response_message["message"].get("request_id", "")

    # Look through all MAIL instances to find one with pending requests
    mail_instance = None
    for user_id, user_mail in user_mail_instances.items():
        if task_id in user_mail.pending_requests:
            mail_instance = user_mail
            break

    if not mail_instance:
        for swarm_id, swarm_mail in swarm_mail_instances.items():
            if task_id in swarm_mail.pending_requests:
                mail_instance = swarm_mail
                break

    if mail_instance:
        # Modify the response message to ensure it gets routed to the supervisor
        # The supervisor needs to process this response and generate a final response for the user

        # Extract the original sender (which should be the supervisor)
        original_sender = response_message["message"].get("recipient", "supervisor")
        if "@" in original_sender:
            original_sender = original_sender.split("@")[0]

        # Create a new message that the supervisor can process
        supervisor_message = MAILMessage(
            id=str(uuid.uuid4()),
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            message=MAILResponse(
                task_id=response_message["message"]["task_id"],
                request_id=response_message["message"].get(
                    "request_id", response_message["message"]["task_id"]
                ),
                sender=response_message["message"]["sender"],
                recipient=original_sender,  # Route back to the original sender (supervisor)
                subject=f"Response from {response_message['message']['sender']}: {response_message['message']['subject']}",
                body=response_message["message"]["body"],
                sender_swarm=response_message["message"].get("sender_swarm"),
                recipient_swarm=local_swarm_name,
            ),
            msg_type="response",
        )

        # Submit the modified response to the MAIL instance
        await mail_instance.handle_interswarm_response(supervisor_message)
        logger.info(f"response submitted to MAIL instance for task '{task_id}'")
        return {"status": "response_processed", "task_id": task_id}
    else:
        logger.warning(f"no MAIL instance found for task '{task_id}'")
        return {"status": "no_mail_instance", "task_id": task_id}


async def _send_response_to_swarm(
    target_swarm: str, response_message: MAILMessage
) -> None:
    """Send a response message to a specific swarm via HTTP."""
    global swarm_registry

    try:
        endpoint = swarm_registry.get_swarm_endpoint(target_swarm)
        if not endpoint:
            logger.error(f"unknown swarm endpoint: '{target_swarm}'")
            return

        if not endpoint["is_active"]:
            logger.warning(f"swarm '{target_swarm}' is not active")
            return

        # ensure both the sender and recipient are in the format of "agent@swarm"
        response_message["message"]["sender"] = format_agent_address(
            response_message["message"]["sender"]["address"], local_swarm_name
        )
        # response_message["message"]["recipient"] = format_agent_address(response_message["message"]["recipient"]["address"], target_swarm)

        # Send response via HTTP
        url = f"{endpoint['base_url']}/interswarm/response"
        headers = {
            "Content-Type": "application/json",
            "User-Agent": f"MAIL-Interswarm-Router/{local_swarm_name}",
        }

        auth_token = swarm_registry.get_resolved_auth_token(target_swarm)
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=response_message, headers=headers, timeout=timeout
            ) as response:
                if response.status == 200:
                    logger.info(
                        f"successfully sent response to swarm: '{target_swarm}'"
                    )
                else:
                    logger.error(
                        f"failed to send response to swarm '{target_swarm}' with status: '{response.status}'"
                    )

    except Exception as e:
        logger.error(
            f"error sending response to swarm '{target_swarm}' with error: '{e}'"
        )


@app.post("/interswarm/send")
async def send_interswarm_message(request: Request):
    """Send an interswarm message to another swarm."""
    global swarm_registry, user_mail_instances

    try:
        # auth process
        api_key = request.headers.get("Authorization")
        if api_key is None:
            logger.warning("no API key provided")
            raise HTTPException(status_code=401, detail="no API key provided")

        if api_key.startswith("Bearer "):
            jwt = await login(api_key.split(" ")[1])
            logger.info(f"response received with token: '{jwt[:8]}...'...")
        else:
            logger.warning("invalid API key format")
            raise HTTPException(status_code=401, detail="invalid API key format")

        token_info = await get_token_info(jwt)
        role = token_info["role"]
        if (role != "user") and (role != "admin"):
            logger.warning("invalid role")
            raise HTTPException(status_code=401, detail="invalid role")
        user_id = generate_user_id(token_info)

        # parse request
        data = await request.json()
        target_agent = data.get("target_agent")
        message_content = data.get("message")
        user_token = data.get("user_token")

        if not target_agent or not message_content:
            raise HTTPException(
                status_code=400, detail="target_agent and message are required"
            )

        if not user_token or user_token not in user_mail_instances:
            raise HTTPException(status_code=400, detail="Valid user_token is required")

        mail_instance = user_mail_instances[user_token]

        # Create MAIL message
        mail_message = MAILMessage(
            id=str(uuid.uuid4()),
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            message=MAILRequest(
                task_id=str(uuid.uuid4()),
                request_id=str(uuid.uuid4()),
                sender=create_user_address(f"{user_id}@{local_swarm_name}"),
                recipient=create_agent_address(f"{target_agent}"),
                subject="Interswarm Message",
                body=message_content,
                sender_swarm=local_swarm_name,
                recipient_swarm=target_agent.split("@")[1],
            ),
            msg_type="request",
        )

        # Route the message
        if mail_instance.interswarm_router:
            response = await mail_instance.interswarm_router.route_message(mail_message)
            return response
        else:
            raise HTTPException(
                status_code=503, detail="Interswarm router not available"
            )

    except Exception as e:
        logger.error(f"error sending interswarm message: '{e}'")
        raise HTTPException(
            status_code=500, detail=f"error sending interswarm message: '{str(e)}'"
        )


@app.post("/swarms/load")
async def load_swarm_from_json(request: Request):
    global persistent_swarm

    # got to let them know (shouting emoji)
    logger.info("Send swarm endpoint accessed")

    # verify that we have a key
    api_key = request.headers.get("Authorization")
    if api_key is None:
        logger.warning("no API key provided")
        raise HTTPException(status_code=401, detail="no API key provided")
    
    # check that the key matches the bearer pattern
    if api_key.startswith("Bearer "):
        jwt = await login(api_key.split(" ")[1])
        logger.info(f"load swarm accessed with token: '{jwt[:8]}...'...")
    else:
        logger.warning("invalid API key format")
        raise HTTPException(status_code=401, detail="invalid API key format")
    
    # make sure the load endpoint was hit by an admin
    token_info = await get_token_info(jwt)
    role = token_info["role"]
    if role != "admin":
        logger.warning("invalid role for building swarm")
        raise HTTPException(status_code=401, detail="invalid role for building swarm")
    
    # get the json string from the request
    data = await request.json()
    swarm_json = data.get("json")

    try:
        # try to load the swarm from string and set the persistent swarm
        swarm = build_swarm_from_json_str(swarm_json)
        persistent_swarm = swarm
        return {"status": "success", "swarm_name": swarm.name}
    except Exception as e:
        # shit hit the fan
        logger.error(f"error loading swarm from JSON: {e}")
        raise HTTPException(
            status_code=500, detail=f"error loading swarm from JSON: {e}"
        )


if __name__ == "__main__":
    logger.info("starting MAIL server directly...")
    port = int(os.getenv("BASE_URL", "http://localhost:8000").split(":")[-1])
    uvicorn.run("mail.server:app", host="0.0.0.0", port=port, reload=True)
