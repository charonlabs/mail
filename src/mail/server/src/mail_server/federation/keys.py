# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""Ed25519 key loading and manifest serialization for federation."""

from __future__ import annotations

import base64
import hmac
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from mail_protocol.core.federation import MAILFederationPublicKey


class FederationKeyError(ValueError):
    """Raised when federation key material is missing or unsafe."""


@dataclass(frozen=True, slots=True)
class FederationPrivateKey:
    """An active private key and its public manifest representation."""

    key_id: str
    private_key: Ed25519PrivateKey
    public_key_base64: str

    def manifest_key(self) -> MAILFederationPublicKey:
        """Return the public-only discovery representation."""

        return MAILFederationPublicKey(
            key_id=self.key_id,
            algorithm="ed25519",
            public_key=self.public_key_base64,
        )


def _public_key_base64(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


def load_federation_private_key(
    path: str | Path,
    *,
    key_id: str,
    expected_public_key: str | None = None,
) -> FederationPrivateKey:
    """Load an unencrypted PKCS8/PEM Ed25519 key from a private regular file."""

    key_path = Path(path)
    try:
        file_stat = key_path.lstat()
    except OSError as exc:
        raise FederationKeyError("federation private key file is not readable") from exc

    if stat.S_ISLNK(file_stat.st_mode) or not stat.S_ISREG(file_stat.st_mode):
        raise FederationKeyError("federation private key must be a regular file")
    if os.name == "posix" and file_stat.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise FederationKeyError(
            "federation private key must not grant group or other permissions"
        )
    if os.name == "posix" and hasattr(os, "geteuid"):
        if file_stat.st_uid != os.geteuid():
            raise FederationKeyError(
                "federation private key must be owned by the server process user"
            )

    try:
        pem = key_path.read_bytes()
        private_key = serialization.load_pem_private_key(pem, password=None)
    except (OSError, TypeError, ValueError) as exc:
        raise FederationKeyError(
            "federation private key must be an unencrypted PEM private key"
        ) from exc
    if not isinstance(private_key, Ed25519PrivateKey):
        raise FederationKeyError("federation private key must use Ed25519")

    public_key_base64 = _public_key_base64(private_key.public_key())
    if expected_public_key is not None and not hmac.compare_digest(
        public_key_base64, expected_public_key
    ):
        raise FederationKeyError(
            "federation private key does not match the advertised public key"
        )

    # Reuse the protocol model's key-ID grammar and public-key validation.
    try:
        MAILFederationPublicKey(
            key_id=key_id,
            algorithm="ed25519",
            public_key=public_key_base64,
        )
    except ValueError as exc:
        raise FederationKeyError("invalid federation key ID") from exc

    return FederationPrivateKey(
        key_id=key_id,
        private_key=private_key,
        public_key_base64=public_key_base64,
    )


def public_key_from_manifest(key: MAILFederationPublicKey) -> Ed25519PublicKey:
    """Convert a validated discovery key to a cryptography public key."""

    try:
        return Ed25519PublicKey.from_public_bytes(base64.b64decode(key.public_key))
    except (TypeError, ValueError) as exc:
        raise FederationKeyError("invalid Ed25519 public key") from exc
