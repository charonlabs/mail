# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from pathlib import Path
from typing import Any

from mail.api import action

FILE_READ_PARAMETERS = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "The path to the file to read",
        },
    },
    "required": ["path"],
}


@action(
    name="read_file",
    description="Read a file from the filesystem",
    parameters=FILE_READ_PARAMETERS,
)
async def read_file(args: dict[str, Any]) -> str:
    """
    Read a file from the filesystem.
    """
    path = args.get("path")

    if not isinstance(path, str):
        return "Error: `path` must be a string"

    target = Path(path)
    if not target.exists():
        return f"Error: file not found at {path}"
    if not target.is_file():
        return f"Error: {path} is not a file"

    try:
        return target.read_text()
    except Exception as e:
        return f"Error: {e}"


FILE_WRITE_PARAMETERS = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "The path to the file to write to",
        },
        "content": {
            "type": "string",
            "description": "The content to write to the file",
        },
    },
}


@action(
    name="write_file",
    description="Write to a file on the filesystem",
    parameters=FILE_WRITE_PARAMETERS,
)
async def write_file(args: dict[str, Any]) -> str:
    """
    Write to a file on the filesystem.
    """
    path = args.get("path")
    content = args.get("content")

    if not isinstance(path, str):
        return "Error: `path` must be a string"
    if not isinstance(content, str):
        return "Error: `content` must be a string"

    target = Path(path)
    if not target.exists():
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
            return f"successfully wrote to {path}"
        except Exception as e:
            return f"Error: {e}"

    if not target.is_file():
        return f"Error: {path} is not a file"

    try:
        target.write_text(content)
        return f"successfully wrote to {path}"
    except Exception as e:
        return f"Error: {e}"


FILE_DELETE_PARAMETERS = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "The path to the file to delete",
        },
    },
    "required": ["path"],
}


@action(
    name="delete_file",
    description="Delete a file from the filesystem",
    parameters=FILE_DELETE_PARAMETERS,
)
async def delete_file(args: dict[str, Any]) -> str:
    """
    Delete a file from the filesystem.
    """
    path = args.get("path")
    if not isinstance(path, str):
        return "Error: `path` must be a string"

    target = Path(path)
    if not target.exists():
        return f"Error: file not found at {path}"
    if not target.is_file():
        return f"Error: {path} is not a file"

    try:
        target.unlink()
        return f"successfully deleted {path}"
    except Exception as e:
        return f"Error: {e}"


DIR_CREATE_PARAMETERS = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "The path to the directory to create",
        },
    },
    "required": ["path"],
}


@action(
    name="create_directory",
    description="Create a directory on the filesystem",
    parameters=DIR_CREATE_PARAMETERS,
)
async def create_directory(args: dict[str, Any]) -> str:
    """
    Create a directory on the filesystem.
    """
    path = args["path"]
    if not isinstance(path, str):
        return "Error: `path` must be a string"

    target = Path(path)
    if target.exists() and target.is_dir():
        return f"Error: directory already exists at {path}"
    if target.exists() and target.is_file():
        return f"Error: {path} is a file, not a directory"

    try:
        target.mkdir(parents=True, exist_ok=False)
        return f"successfully created directory at {path}"
    except Exception as e:
        return f"Error: {e}"


DIR_READ_PARAMETERS = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "The path to the directory to read",
        },
    },
    "required": ["path"],
}


@action(
    name="read_directory",
    description="Read a directory on the filesystem",
    parameters=DIR_READ_PARAMETERS,
)
async def read_directory(args: dict[str, Any]) -> str:
    """
    Read a directory on the filesystem.
    """
    path = args.get("path")
    if not isinstance(path, str):
        return "Error: `path` must be a string"

    target = Path(path)
    if not target.exists():
        return f"Error: directory not found at {path}"
    if not target.is_dir():
        return f"Error: {path} is not a directory"

    try:
        entries = sorted(target.iterdir(), key=lambda p: p.name)
        return "\n".join(entry.name for entry in entries)
    except Exception as e:
        return f"Error: {e}"
