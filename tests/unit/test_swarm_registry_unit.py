from mail.swarm_registry import SwarmRegistry


def test_register_persist_and_resolve_token(tmp_path, monkeypatch):
    reg_file = tmp_path / "reg.json"
    # Ensure environment has the expected variable for resolving
    monkeypatch.setenv("SWARM_AUTH_TOKEN_REMOTE", "secret-token")

    reg = SwarmRegistry("example", "http://localhost:8000", str(reg_file))
    reg.register_swarm(
        "remote", "http://remote:9999", auth_token="anything", volatile=False
    )

    # Token reference should be env-style in memory
    ep = reg.get_swarm_endpoint("remote")
    assert ep is not None and ep["is_active"] is True
    # get_resolved_auth_token should yield the env var value
    assert reg.get_resolved_auth_token("remote") == "secret-token"

    # Persist and reload into a fresh registry
    reg.save_persistent_endpoints()
    reg2 = SwarmRegistry("example", "http://localhost:8000", str(reg_file))
    ep2 = reg2.get_swarm_endpoint("remote")
    assert ep2 is not None
    # Loaded entry will store resolved token in auth_token_ref field
    assert ep2.get("auth_token_ref") == "secret-token"


def test_migrate_and_validate_env_vars(tmp_path, monkeypatch):
    reg = SwarmRegistry("example", "http://localhost:8000", str(tmp_path / "r.json"))
    # Register a volatile swarm so the raw token is kept directly
    reg.register_swarm("other", "http://other", auth_token="abc", volatile=True)

    # Migrate to env refs
    reg.migrate_auth_tokens_to_env_refs(env_var_prefix="TEST_TOKEN")
    ep = reg.get_swarm_endpoint("other")
    assert ep is not None and ep.get("auth_token_ref") == "${TEST_TOKEN_OTHER}"

    # Validation should report that env var is missing
    results = reg.validate_environment_variables()
    assert results.get("TEST_TOKEN_OTHER") is False
