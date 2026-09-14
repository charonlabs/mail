# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""Unit tests for federation Ed25519 key handling."""

from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from mail_server.federation.keys import (
    FederationKeyError,
    load_federation_private_key,
    public_key_from_manifest,
)


def write_private_key(path: Path, key: Ed25519PrivateKey, mode: int = 0o600) -> None:
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    path.chmod(mode)


def test_load_private_key_derives_public_manifest_key(tmp_path: Path) -> None:
    path = tmp_path / "federation.pem"
    write_private_key(path, Ed25519PrivateKey.generate())

    loaded = load_federation_private_key(path, key_id="active-2026-09")
    manifest_key = loaded.manifest_key()

    assert manifest_key.key_id == "active-2026-09"
    assert manifest_key.public_key == loaded.public_key_base64
    public_key_from_manifest(manifest_key).verify(
        loaded.private_key.sign(b"probe"),
        b"probe",
    )


def test_load_private_key_compares_advertised_public_key(tmp_path: Path) -> None:
    path = tmp_path / "federation.pem"
    write_private_key(path, Ed25519PrivateKey.generate())

    with pytest.raises(FederationKeyError, match="does not match"):
        load_federation_private_key(
            path,
            key_id="active",
            expected_public_key="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        )


def test_load_private_key_rejects_open_permissions(tmp_path: Path) -> None:
    path = tmp_path / "federation.pem"
    write_private_key(path, Ed25519PrivateKey.generate(), mode=0o640)

    with pytest.raises(FederationKeyError, match="group or other"):
        load_federation_private_key(path, key_id="active")


def test_load_private_key_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target.pem"
    write_private_key(target, Ed25519PrivateKey.generate())
    link = tmp_path / "federation.pem"
    link.symlink_to(target)

    with pytest.raises(FederationKeyError, match="regular file"):
        load_federation_private_key(link, key_id="active")
