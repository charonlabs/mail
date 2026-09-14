# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""Secure primitives used by MAIL Federation v1."""

from mail_server.federation.discovery import (
    FederationDiscoveryClient,
    FederationDiscoveryError,
    FederationHostRejected,
    FederationManifestError,
    FederationUnknownKey,
    ResolvedFederationKey,
)
from mail_server.federation.keys import (
    FederationKeyError,
    FederationPrivateKey,
    load_federation_private_key,
    public_key_from_manifest,
)
from mail_server.federation.signatures import (
    FEDERATION_COVERED_COMPONENTS,
    FederationSignatureError,
    SignedFederationRequest,
    VerifiedFederationSignature,
    serialize_federation_envelope,
    sign_federation_request,
    verify_federation_request,
    verify_federation_request_with_discovery,
)

__all__ = [
    "FEDERATION_COVERED_COMPONENTS",
    "FederationDiscoveryClient",
    "FederationDiscoveryError",
    "FederationHostRejected",
    "FederationKeyError",
    "FederationManifestError",
    "FederationPrivateKey",
    "FederationSignatureError",
    "FederationUnknownKey",
    "ResolvedFederationKey",
    "SignedFederationRequest",
    "VerifiedFederationSignature",
    "load_federation_private_key",
    "public_key_from_manifest",
    "serialize_federation_envelope",
    "sign_federation_request",
    "verify_federation_request",
    "verify_federation_request_with_discovery",
]
