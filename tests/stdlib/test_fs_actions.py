# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from pathlib import Path

import pytest

from mail.stdlib.fs import (
    create_directory,
    delete_file,
    read_directory,
    read_file,
    write_file,
)


@pytest.mark.asyncio
async def test_write_and_read_file_creates_parent(tmp_path: Path) -> None:
    """
    Test that the write file action creates the parent directory if it doesn't exist.
    """
    file_path = tmp_path / "subdir" / "note.txt"

    write_result = await write_file.function(  # type: ignore[arg-type]
        {"path": file_path.as_posix(), "content": "hello"}
    )
    assert write_result == f"successfully wrote to {file_path.as_posix()}"
    assert file_path.read_text() == "hello"

    read_result = await read_file.function({"path": file_path.as_posix()})  # type: ignore[arg-type]
    assert read_result == "hello"


@pytest.mark.asyncio
async def test_write_rejects_non_string_content(tmp_path: Path) -> None:
    """
    Test that the write file action rejects non-string content.
    """
    result = await write_file.function(
        {"path": str(tmp_path / "file.txt"), "content": 123}
    )  # type: ignore[arg-type]
    assert result.startswith("Error")


@pytest.mark.asyncio
async def test_delete_file(tmp_path: Path) -> None:
    """
    Test that the delete file action deletes a file.
    """
    target = tmp_path / "data.txt"
    target.write_text("payload")

    delete_result = await delete_file.function({"path": target.as_posix()})  # type: ignore[arg-type]
    assert delete_result == f"successfully deleted {target.as_posix()}"
    assert not target.exists()


@pytest.mark.asyncio
async def test_create_directory_and_listing(tmp_path: Path) -> None:
    """
    Test that the create directory and read directory actions work together.
    """
    directory = tmp_path / "workspace"

    create_result = await create_directory.function({"path": directory.as_posix()})  # type: ignore[arg-type]
    assert create_result == f"successfully created directory at {directory.as_posix()}"

    (directory / "a.txt").write_text("a")
    (directory / "b.txt").write_text("b")

    list_result = await read_directory.function({"path": directory.as_posix()})  # type: ignore[arg-type]
    assert list_result.splitlines() == ["a.txt", "b.txt"]


@pytest.mark.asyncio
async def test_create_directory_errors_when_file_exists(tmp_path: Path) -> None:
    """
    Test that the create directory action errors when the path is a file.
    """
    file_path = tmp_path / "artifact"
    file_path.write_text("content")

    result = await create_directory.function({"path": file_path.as_posix()})  # type: ignore[arg-type]
    assert result.startswith("Error")


@pytest.mark.asyncio
async def test_read_directory_errors_for_missing(tmp_path: Path) -> None:
    """
    Test that the read directory action errors for a missing directory.
    """
    result = await read_directory.function({"path": str(tmp_path / "missing")})  # type: ignore[arg-type]
    assert result.startswith("Error")
