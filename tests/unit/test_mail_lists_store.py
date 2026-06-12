# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from mail_protocol.core.lists import MAILListInBackend, MAILListPolicy
from mail_protocol.core.user_agents import MAILAdmin
from mail_protocol.network.requests import (
    AdminListPatchRequest,
    AdminListPostRequest,
)
from mail_server.backends.memory import fs as memory_fs
from mail_server.backends.memory.api import MemoryBackend

# ─── fs persistence ─────────────────────────────────────────────────


def _seed_list(deployment_dir: Path) -> MAILListInBackend:
    now = datetime(2026, 6, 4, 0, 0, tzinfo=UTC)
    record = MAILListInBackend(
        name="welfare-discourse",
        swarm="chorus",
        host="localhost",
        owner="admin:ryan@localhost",
        members=["philosopher@chorus@localhost"],
        policy=MAILListPolicy(),
        list_id="11111111-1111-1111-1111-111111111111",
        created_at=now,
        updated_at=now,
    )
    (deployment_dir / "lists" / record.get_address()).write_text(
        record.model_dump_json(),
        encoding="utf-8",
    )
    return record


@pytest.mark.asyncio
async def test_load_lists_reads_valid_entries(deployment_dir: Path) -> None:
    seeded = _seed_list(deployment_dir)
    loaded = await memory_fs.load_lists()
    assert seeded.get_address() in loaded
    assert loaded[seeded.get_address()].name == "welfare-discourse"
    assert loaded[seeded.get_address()].members == [
        "philosopher@chorus@localhost"
    ]


@pytest.mark.asyncio
async def test_load_lists_skips_invalid_filenames(deployment_dir: Path) -> None:
    _seed_list(deployment_dir)
    # A filename that does NOT parse as a MAIL address must be skipped.
    (deployment_dir / "lists" / "not-an-address").write_text(
        "{}", encoding="utf-8"
    )
    loaded = await memory_fs.load_lists()
    # Only the valid entry survives.
    assert len(loaded) == 1
    assert "list:welfare-discourse@chorus@localhost" in loaded


@pytest.mark.asyncio
async def test_load_lists_skips_malformed_json(deployment_dir: Path) -> None:
    # Filename validates as a MAIL list address but the body is bad JSON.
    target = (
        deployment_dir
        / "lists"
        / "list:welfare-discourse@chorus@localhost"
    )
    target.write_text("not-json", encoding="utf-8")
    loaded = await memory_fs.load_lists()
    assert loaded == {}


@pytest.mark.asyncio
async def test_save_lists_round_trips_via_load(deployment_dir: Path) -> None:
    record = _seed_list(deployment_dir)
    # Clear the file and re-write via save_lists.
    (deployment_dir / "lists" / record.get_address()).unlink()
    await memory_fs.save_lists({record.get_address(): record})

    written = (deployment_dir / "lists" / record.get_address()).read_text(
        encoding="utf-8"
    )
    parsed = json.loads(written)
    assert parsed["name"] == "welfare-discourse"
    assert parsed["members"] == ["philosopher@chorus@localhost"]

    reloaded = await memory_fs.load_lists()
    assert reloaded == {record.get_address(): record}


# ─── MemoryBackend storage methods ─────────────────────────────────


def _make_admin() -> MAILAdmin:
    return MAILAdmin(
        ua_type="admin",
        admin_id="ryan",
        host="localhost",
    )


def _make_post_request(
    *,
    members: list[str] | None = None,
    policy: MAILListPolicy | None = None,
) -> AdminListPostRequest:
    return AdminListPostRequest(
        name="welfare-discourse",
        swarm_name="chorus",
        owner="admin:ryan@localhost",
        members=members or [],
        policy=policy or MAILListPolicy(),
    )


@pytest.mark.asyncio
async def test_admin_post_list_creates_record(backend: MemoryBackend) -> None:
    admin = _make_admin()
    record = await backend.admin_post_list(admin, _make_post_request())
    assert record.name == "welfare-discourse"
    assert record.host == "localhost"
    assert record.list_id  # uuid string
    assert record.created_at == record.updated_at
    assert record.get_address() in backend.lists


@pytest.mark.asyncio
async def test_admin_post_list_rejects_duplicate_address(
    backend: MemoryBackend,
) -> None:
    admin = _make_admin()
    await backend.admin_post_list(admin, _make_post_request())
    with pytest.raises(ValueError, match="already taken"):
        await backend.admin_post_list(admin, _make_post_request())


@pytest.mark.asyncio
async def test_admin_get_lists_returns_all_records(
    backend: MemoryBackend,
) -> None:
    admin = _make_admin()
    await backend.admin_post_list(admin, _make_post_request())
    await backend.admin_post_list(
        admin,
        AdminListPostRequest(
            name="alignment",
            swarm_name="chorus",
            owner="admin:ryan@localhost",
        ),
    )
    lists = await backend.admin_get_lists(admin)
    assert {ml.name for ml in lists} == {"welfare-discourse", "alignment"}


@pytest.mark.asyncio
async def test_admin_get_list_returns_specific_record(
    backend: MemoryBackend,
) -> None:
    admin = _make_admin()
    posted = await backend.admin_post_list(admin, _make_post_request())
    fetched = await backend.admin_get_list(admin, posted.get_address())
    assert fetched == posted


@pytest.mark.asyncio
async def test_admin_get_list_raises_for_missing(
    backend: MemoryBackend,
) -> None:
    admin = _make_admin()
    with pytest.raises(ValueError, match="not found"):
        await backend.admin_get_list(
            admin,
            "list:nonexistent@chorus@localhost",
        )


@pytest.mark.asyncio
async def test_admin_patch_list_updates_policy(
    backend: MemoryBackend,
) -> None:
    admin = _make_admin()
    posted = await backend.admin_post_list(admin, _make_post_request())
    address = posted.get_address()

    new_policy = MAILListPolicy(
        visibility="private",
        join_policy="approval",
        send_policy="members-only",
    )
    updated = await backend.admin_patch_list(
        admin,
        address,
        AdminListPatchRequest(policy=new_policy),
    )
    assert updated.policy.visibility == "private"
    assert updated.policy.join_policy == "approval"
    assert updated.policy.send_policy == "members-only"
    assert updated.updated_at >= posted.updated_at


@pytest.mark.asyncio
async def test_admin_patch_list_empty_payload_is_noop(
    backend: MemoryBackend,
) -> None:
    admin = _make_admin()
    posted = await backend.admin_post_list(admin, _make_post_request())
    address = posted.get_address()
    result = await backend.admin_patch_list(
        admin,
        address,
        AdminListPatchRequest(),
    )
    assert result == posted


@pytest.mark.asyncio
async def test_admin_patch_list_raises_for_missing(
    backend: MemoryBackend,
) -> None:
    admin = _make_admin()
    with pytest.raises(ValueError, match="not found"):
        await backend.admin_patch_list(
            admin,
            "list:nonexistent@chorus@localhost",
            AdminListPatchRequest(policy=MAILListPolicy()),
        )


@pytest.mark.asyncio
async def test_admin_delete_list_removes_record(
    backend: MemoryBackend,
) -> None:
    admin = _make_admin()
    posted = await backend.admin_post_list(admin, _make_post_request())
    address = posted.get_address()

    removed = await backend.admin_delete_list(admin, address)
    assert removed == posted
    assert address not in backend.lists


@pytest.mark.asyncio
async def test_admin_delete_list_raises_for_missing(
    backend: MemoryBackend,
) -> None:
    admin = _make_admin()
    with pytest.raises(ValueError, match="not found"):
        await backend.admin_delete_list(
            admin,
            "list:nonexistent@chorus@localhost",
        )


@pytest.mark.asyncio
async def test_add_list_member_appends(backend: MemoryBackend) -> None:
    admin = _make_admin()
    posted = await backend.admin_post_list(admin, _make_post_request())
    address = posted.get_address()

    updated = await backend.add_list_member(
        address,
        "philosopher@chorus@localhost",
    )
    assert updated.members == ["philosopher@chorus@localhost"]
    assert updated.updated_at >= posted.updated_at


@pytest.mark.asyncio
async def test_add_list_member_is_idempotent(backend: MemoryBackend) -> None:
    admin = _make_admin()
    posted = await backend.admin_post_list(
        admin,
        _make_post_request(members=["philosopher@chorus@localhost"]),
    )
    address = posted.get_address()
    updated = await backend.add_list_member(
        address,
        "philosopher@chorus@localhost",
    )
    # No duplicate; list unchanged.
    assert updated == posted


@pytest.mark.asyncio
async def test_remove_list_member_removes(backend: MemoryBackend) -> None:
    admin = _make_admin()
    posted = await backend.admin_post_list(
        admin,
        _make_post_request(
            members=[
                "philosopher@chorus@localhost",
                "minichorus-pm@minichorus@localhost",
            ]
        ),
    )
    address = posted.get_address()
    updated = await backend.remove_list_member(
        address,
        "philosopher@chorus@localhost",
    )
    assert updated.members == ["minichorus-pm@minichorus@localhost"]


@pytest.mark.asyncio
async def test_remove_list_member_is_idempotent_for_unknown(
    backend: MemoryBackend,
) -> None:
    admin = _make_admin()
    posted = await backend.admin_post_list(admin, _make_post_request())
    address = posted.get_address()
    updated = await backend.remove_list_member(
        address,
        "philosopher@chorus@localhost",
    )
    # Non-member removal returns the list unchanged.
    assert updated == posted


@pytest.mark.asyncio
async def test_add_list_member_raises_for_missing(
    backend: MemoryBackend,
) -> None:
    with pytest.raises(ValueError, match="not found"):
        await backend.add_list_member(
            "list:nonexistent@chorus@localhost",
            "philosopher@chorus@localhost",
        )


@pytest.mark.asyncio
async def test_remove_list_member_raises_for_missing(
    backend: MemoryBackend,
) -> None:
    with pytest.raises(ValueError, match="not found"):
        await backend.remove_list_member(
            "list:nonexistent@chorus@localhost",
            "philosopher@chorus@localhost",
        )


# ─── Lifecycle integration ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_on_server_shutdown_persists_lists(
    backend: MemoryBackend,
    deployment_dir: Path,
) -> None:
    admin = _make_admin()
    posted = await backend.admin_post_list(admin, _make_post_request())
    await backend.on_server_shutdown()

    written = (deployment_dir / "lists" / posted.get_address()).read_text(
        encoding="utf-8"
    )
    parsed = json.loads(written)
    assert parsed["name"] == "welfare-discourse"
    assert parsed["list_id"] == posted.list_id


@pytest.mark.asyncio
async def test_on_server_startup_restores_lists(
    deployment_dir: Path,
) -> None:
    seeded = _seed_list(deployment_dir)
    backend = MemoryBackend()
    await backend.on_server_startup(host="localhost")
    assert seeded.get_address() in backend.lists
    assert backend.lists[seeded.get_address()].name == "welfare-discourse"


# Silence the async-fixture warning for the parametrized fixture above.
_ = asyncio
