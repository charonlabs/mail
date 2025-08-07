# Simplified FastAPI server for ACP over HTTP

import datetime
import logging
import uuid
import asyncio
from contextlib import asynccontextmanager
from typing import Dict

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from toml import load as load_toml

from acp.logger import init_logger

# Initialize logger at module level so it runs regardless of how the server is started
init_logger()
logger = logging.getLogger("acp")

# Global variables to hold the persistent swarm and user-specific ACP instances
persistent_swarm = None
user_acp_instances: Dict[str, dict] = {}
user_acp_tasks: Dict[str, asyncio.Task] = {}

app = FastAPI()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    # Startup
    logger.info("ACP server starting up...")
    
    # Create persistent swarm at startup
    global persistent_swarm
    try:
        logger.info("Building persistent swarm...")
        # For now, just create a simple swarm object
        persistent_swarm = {"name": "example", "status": "ready"}
        logger.info("Persistent swarm built successfully")
    except Exception as e:
        logger.error(f"Error building persistent swarm: {e}")
        raise e
    
    yield
    
    # Shutdown
    logger.info("ACP server shutting down...")
    
    # Clean up all user ACP instances
    global user_acp_instances, user_acp_tasks
    for user_token, acp_task in user_acp_tasks.items():
        if acp_task and not acp_task.done():
            logger.info(f"Cancelling ACP task for user: {user_token[:8]}...")
            acp_task.cancel()
            try:
                await acp_task
            except asyncio.CancelledError:
                pass


async def get_or_create_user_acp(user_token: str) -> dict:
    """
    Get or create an ACP instance for a specific user.
    Each user gets their own isolated ACP instance.
    """
    global persistent_swarm, user_acp_instances, user_acp_tasks
    
    if user_token not in user_acp_instances:
        try:
            logger.info(f"Creating ACP instance for user: {user_token[:8]}...")
            
            # Create a new ACP instance for this user
            user_acp_instances[user_token] = {
                "user_token": user_token,
                "status": "running",
                "message_count": 0,
                "agent_histories": {},  # Each user has their own agent histories
                "pending_requests": {}  # Each user has their own pending requests
            }
            
            # Start the ACP instance in continuous mode for this user
            logger.info(f"Starting ACP continuous mode for user: {user_token[:8]}...")
            acp_task = asyncio.create_task(simulate_acp_continuous(user_token))
            user_acp_tasks[user_token] = acp_task
            
            logger.info(f"ACP instance created and started for user: {user_token[:8]}")
            
        except Exception as e:
            logger.error(f"Error creating ACP instance for user {user_token[:8]}: {e}")
            raise e
    
    return user_acp_instances[user_token]


async def simulate_acp_continuous(user_token: str):
    """Simulate continuous ACP operation for a specific user."""
    user_id = user_token[:8]
    logger.info(f"Simulating continuous ACP operation for user {user_id}...")
    try:
        while True:
            await asyncio.sleep(1)  # Simulate background processing
    except asyncio.CancelledError:
        logger.info(f"ACP continuous operation cancelled for user {user_id}")
    except Exception as e:
        logger.error(f"Error in continuous ACP operation for user {user_id}: {e}")


async def submit_and_wait_simple(user_token: str, message: str, timeout: float = 30.0) -> str:
    """
    Simplified submit and wait function that simulates ACP processing for a specific user.
    """
    global user_acp_instances
    
    if user_token not in user_acp_instances:
        raise Exception(f"ACP instance not initialized for user {user_token[:8]}")
    
    user_acp = user_acp_instances[user_token]
    
    # Simulate processing time
    await asyncio.sleep(0.1)
    
    # Increment message count for this user
    user_acp["message_count"] += 1
    
    # Return a simple response with user-specific information
    return f"Processed message for user {user_token[:8]}: {message} (Message #{user_acp['message_count']})"


@app.get("/")
async def root():
    logger.info("Root endpoint accessed")
    version = load_toml("pyproject.toml")["project"]["version"]
    return {"name": "acp", "status": "ok", "version": version}


@app.get("/status")
async def status(request: Request):
    """Get the status of the persistent swarm and user-specific ACP instances."""
    global persistent_swarm, user_acp_instances, user_acp_tasks
    
    # Get user token from request
    api_key = request.headers.get("Authorization")
    if api_key and api_key.startswith("Bearer "):
        user_token = api_key.split(" ")[1]
        user_acp_status = user_token in user_acp_instances
        user_task_running = user_token in user_acp_tasks and not user_acp_tasks[user_token].done() if user_token in user_acp_tasks else False
        user_message_count = user_acp_instances[user_token]["message_count"] if user_token in user_acp_instances else 0
    else:
        user_acp_status = False
        user_task_running = False
        user_message_count = 0
    
    return {
        "swarm": persistent_swarm,
        "active_users": len(user_acp_instances),
        "user_acp_ready": user_acp_status,
        "user_task_running": user_task_running,
        "user_message_count": user_message_count,
        "all_users": [
            {
                "user_id": token[:8],
                "message_count": acp["message_count"],
                "status": acp["status"]
            }
            for token, acp in user_acp_instances.items()
        ]
    }


@app.post("/chat")
async def chat(request: Request):
    """
    Handle chat requests from the client.
    Uses a user-specific ACP instance to process the request and returns the response.

    Args:
        request: The request object containing the chat message.

    Returns:
        A dictionary containing the response message.
    """
    logger.info("Chat endpoint accessed")

    # auth process (simplified)
    api_key = request.headers.get("Authorization")
    if api_key is None:
        logger.warning("No API key provided")
        raise HTTPException(status_code=401, detail="no API key provided")

    if api_key.startswith("Bearer "):
        user_token = api_key.split(" ")[1]
        logger.info(f"User authenticated with token: {user_token[:8]}...")
    else:
        logger.warning("Invalid API key format")
        raise HTTPException(status_code=401, detail="invalid API key format")

    # Get or create user-specific ACP instance
    try:
        user_acp = await get_or_create_user_acp(user_token)
    except Exception as e:
        logger.error(f"Error getting user ACP instance: {e}")
        raise HTTPException(
            status_code=500, detail=f"error getting user ACP instance: {e.with_traceback(None)}"
        )

    # parse request
    try:
        data = await request.json()
        message = data.get("message", "")
        logger.info(f"Received message from user {user_token[:8]}: {message[:50]}...")
    except Exception as e:
        logger.error(f"Error parsing request: {e}")
        raise HTTPException(
            status_code=400, detail=f"error parsing request: {e.with_traceback(None)}"
        )

    if not message:
        logger.warning("No message provided")
        raise HTTPException(status_code=400, detail="no message provided")

    # ACP process
    try:
        logger.info(f"Processing message with user ACP for user {user_token[:8]}...")
        response = await submit_and_wait_simple(user_token, message)
        logger.info(f"ACP completed successfully for user {user_token[:8]}")
        return {"response": response}
    except Exception as e:
        logger.error(f"Error processing message for user {user_token[:8]}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"error processing message: {e.with_traceback(None)}",
        )


if __name__ == "__main__":
    logger.info("Starting ACP server directly...")
    uvicorn.run("acp.server_simple:app", host="0.0.0.0", port=8000, reload=True)
