# Simple FastAPI server for MAIL over HTTP

import datetime
import logging
import uuid
import asyncio
from contextlib import asynccontextmanager
from typing import Dict

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from toml import load as load_toml

from .core import MAIL
from .message import MAILMessage, MAILRequest
from .logger import init_logger
from .swarms.builder import build_swarm_from_name
from .auth import login

# Initialize logger at module level so it runs regardless of how the server is started
init_logger()
logger = logging.getLogger("mail")

# Global variables to hold the persistent swarm and user-specific MAIL instances
persistent_swarm = None
user_mail_instances: Dict[str, dict] = {}
user_mail_tasks: Dict[str, asyncio.Task] = {}

app = FastAPI()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    # Startup
    logger.info("MAIL server starting up...")

    # Create persistent swarm at startup
    global persistent_swarm
    try:
        logger.info("building persistent swarm...")
        # For now, just create a simple swarm object
        persistent_swarm = {"name": "example", "status": "ready"}
        logger.info("persistent swarm built successfully")
    except Exception as e:
        logger.error(f"error building persistent swarm: '{e}'")
        raise e

    yield

    # Shutdown
    logger.info("MAIL server shutting down...")

    # Clean up all user MAIL instances
    global user_mail_instances, user_mail_tasks
    for user_token, mail_task in user_mail_tasks.items():
        if mail_task and not mail_task.done():
            logger.info(f"cancelling MAIL task for user: '{user_token[:8]}...'")
            mail_task.cancel()
            try:
                await mail_task
            except asyncio.CancelledError:
                pass


async def get_or_create_user_mail(user_token: str) -> dict:
    """
    Get or create a MAIL instance for a specific user.
    Each user gets their own isolated MAIL instance.
    """
    global persistent_swarm, user_mail_instances, user_mail_tasks

    if user_token not in user_mail_instances:
        try:
            logger.info(f"creating MAIL instance for user: '{user_token[:8]}...'")

            # Create a new MAIL instance for this user
            user_mail_instances[user_token] = {
                "user_token": user_token,
                "status": "running",
                "message_count": 0,
                "agent_histories": {},  # Each user has their own agent histories
                "pending_requests": {},  # Each user has their own pending requests
            }

            # Start the MAIL instance in continuous mode for this user
            logger.info(
                f"starting MAIL continuous mode for user: '{user_token[:8]}...'"
            )
            mail_task = asyncio.create_task(simulate_mail_continuous(user_token))
            user_mail_tasks[user_token] = mail_task

            logger.info(
                f"MAIL instance created and started for user: '{user_token[:8]}...'"
            )

        except Exception as e:
            logger.error(
                f"error creating MAIL instance for user '{user_token[:8]}...' with error: '{e}'"
            )
            raise e

    return user_mail_instances[user_token]


async def simulate_mail_continuous(user_token: str):
    """Simulate continuous MAIL operation for a specific user."""
    user_id = user_token[:8]
    logger.info(f"simulating continuous MAIL operation for user '{user_id}'...")
    try:
        while True:
            await asyncio.sleep(1)  # Simulate background processing
    except asyncio.CancelledError:
        logger.info(f"MAIL continuous operation cancelled for user '{user_id}'")
    except Exception as e:
        logger.error(
            f"error in continuous MAIL operation for user '{user_id}' with error: '{e}'"
        )


async def submit_and_wait_simple(
    user_token: str, message: str, timeout: float = 30.0
) -> str:
    """
    Simplified submit and wait function that simulates MAIL processing for a specific user.
    """
    global user_mail_instances

    if user_token not in user_mail_instances:
        raise Exception(f"MAIL instance not initialized for user '{user_token[:8]}...'")

    user_mail = user_mail_instances[user_token]

    # Simulate processing time
    await asyncio.sleep(0.1)

    # Increment message count for this user
    user_mail["message_count"] += 1

    # Return a simple response with user-specific information
    return f"processed message for user '{user_token[:8]}...': '{message}' (message #{user_mail['message_count']})"


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
        user_token = api_key.split(" ")[1]
        user_mail_status = user_token in user_mail_instances
        user_task_running = (
            user_token in user_mail_tasks and not user_mail_tasks[user_token].done()
            if user_token in user_mail_tasks
            else False
        )
        user_message_count = (
            user_mail_instances[user_token]["message_count"]
            if user_token in user_mail_instances
            else 0
        )
    else:
        user_mail_status = False
        user_task_running = False
        user_message_count = 0

    return {
        "swarm": persistent_swarm,
        "active_users": len(user_mail_instances),
        "user_mail_ready": user_mail_status,
        "user_task_running": user_task_running,
        "user_message_count": user_message_count,
        "all_users": [
            {
                "user_id": token[:8],
                "message_count": mail["message_count"],
                "status": mail["status"],
            }
            for token, mail in user_mail_instances.items()
        ],
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

    # auth process (simplified)
    api_key = request.headers.get("Authorization")
    if api_key is None:
        logger.warning("no API key provided")
        raise HTTPException(status_code=401, detail="no API key provided")

    if api_key.startswith("Bearer "):
        user_token = api_key.split(" ")[1]
        logger.info(f"user authenticated with token: '{user_token[:8]}...'")
    else:
        logger.warning("invalid API key format")
        raise HTTPException(status_code=401, detail="invalid API key format")

    # Get or create user-specific MAIL instance
    try:
        user_mail = await get_or_create_user_mail(user_token)
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
        logger.info(
            f"received message from user '{user_token[:8]}...': '{message[:50]}...'"
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
        logger.info(
            f"processing message with user MAIL for user '{user_token[:8]}...'..."
        )
        response = await submit_and_wait_simple(user_token, message)
        logger.info(f"MAIL completed successfully for user '{user_token[:8]}...'")
        return {"response": response}
    except Exception as e:
        logger.error(
            f"error processing message for user '{user_token[:8]}...' with error: '{e}'"
        )
        raise HTTPException(
            status_code=500,
            detail=f"error processing message: {e.with_traceback(None)}",
        )


if __name__ == "__main__":
    logger.info("starting MAIL server directly...")
    uvicorn.run("mail.server_simple:app", host="0.0.0.0", port=8000, reload=True)
