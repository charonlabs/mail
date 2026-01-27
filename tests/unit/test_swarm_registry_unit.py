# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import json

import pytest

from mail.net.registry import SwarmRegistry


@pytest.mark.asyncio
async def test_register_persist_and_resolve_token(tmp_path, monkeypatch):
    """
    Test that `SwarmRegistry.register_swarm`, `SwarmRegistry.get_swarm_endpoint`, and `SwarmRegistry.get_resolved_auth_token` work as expected, including persistence of metadata.
    """
    reg_file = tmp_path / "reg.json"
    # Ensure environment has the expected variable for resolving
    monkeypatch.setenv("SWARM_AUTH_TOKEN_REMOTE", "secret-token")

    async def fake_remote_info(self, base_url):  # noqa: ARG002
        return {
            "name": "remote",
            "version": "1.0.0",
            "description": "remote swarm",
            "entrypoint": "main",
            "keywords": ["alpha"],
            "public": True,
        }

    monkeypatch.setattr(SwarmRegistry, "_get_remote_swarm_info", fake_remote_info)

    reg = SwarmRegistry(
        "example",
        "http://localhost:8000",
        str(reg_file),
        local_swarm_description="local swarm",
        local_swarm_keywords=["local"],
        local_swarm_public=True,
    )
    await reg.register_swarm(
        "remote",
        "http://remote:9999",
        auth_token="anything",
        metadata={"label": "beta"},
        volatile=False,
    )

    # Token reference should be env-style in memory
    ep = reg.get_swarm_endpoint("remote")
    assert ep is not None and ep["is_active"] is True
    # get_resolved_auth_token should yield the env var value
    assert reg.get_resolved_auth_token("remote") == "secret-token"
    assert ep.get("public") is True
    assert ep.get("keywords") == ["alpha"]

    # Persist and reload into a fresh registry
    reg.save_persistent_endpoints()
    saved = json.loads(reg_file.read_text())
    assert saved["local_swarm_description"] == "local swarm"
    assert saved["local_swarm_keywords"] == ["local"]
    assert saved["local_swarm_public"] is True
    assert saved["endpoints"]["remote"]["public"] is True
    assert saved["endpoints"]["remote"]["keywords"] == ["alpha"]

    reg2 = SwarmRegistry(
        "example",
        "http://localhost:8000",
        str(reg_file),
        local_swarm_description="local swarm",
        local_swarm_keywords=["local"],
        local_swarm_public=True,
    )
    ep2 = reg2.get_swarm_endpoint("remote")
    assert ep2 is not None
    # Loaded entry will store resolved token in auth_token_ref field
    assert ep2.get("auth_token_ref") == "secret-token"
    assert ep2.get("public") is True
    assert ep2.get("keywords") == ["alpha"]


@pytest.mark.asyncio
async def test_migrate_and_validate_env_vars(tmp_path, monkeypatch):
    """
    Test that `SwarmRegistry.migrate_auth_tokens_to_env_refs` and `SwarmRegistry.validate_environment_variables` work as expected.
    """

    async def fake_remote_info(self, base_url):  # noqa: ARG002
        return {
            "name": "other",
            "version": "1.0.0",
            "description": "",
            "entrypoint": "main",
            "keywords": [],
            "public": False,
        }

    monkeypatch.setattr(SwarmRegistry, "_get_remote_swarm_info", fake_remote_info)

    reg = SwarmRegistry("example", "http://localhost:8000", str(tmp_path / "r.json"))
    # Register a volatile swarm so the raw token is kept directly
    await reg.register_swarm("other", "http://other", auth_token="abc", volatile=True)

    # Migrate to env refs
    reg.migrate_auth_tokens_to_env_refs(env_var_prefix="TEST_TOKEN")
    ep = reg.get_swarm_endpoint("other")
    assert ep is not None and ep.get("auth_token_ref") == "${TEST_TOKEN_OTHER}"

    # Validation should report that env var is missing
    results = reg.validate_environment_variables()
    assert results.get("TEST_TOKEN_OTHER") is False
