# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""Secure primitives used by MAIL Federation v1."""

from mail_server.federation.addressing import (
    MessageDeliveryPlan,
    build_message_delivery_plan,
)
from mail_server.federation.bounces import (
    FAILURE_REASONS,
    build_bounce_delivery,
    build_federation_bounces,
    is_dsn,
)
from mail_server.federation.discovery import (
    FederationDeliveryTarget,
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
from mail_server.federation.outbound import (
    FederationDeadLetterEvent,
    FederationHTTPResponse,
    FederationTransportError,
    HTTPFederationTransport,
    OutboundFederationService,
    classify_http_status,
    parse_retry_after,
    retry_delay_for_attempt,
)
from mail_server.federation.records import (
    BounceDelivery,
    BounceEmission,
    InboundFederationReceipt,
    MessageDeliveryTarget,
    OutboundFederationDelivery,
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
from mail_server.federation.worker import FederationWorker

__all__ = [
    "FEDERATION_COVERED_COMPONENTS",
    "FAILURE_REASONS",
    "BounceDelivery",
    "BounceEmission",
    "FederationDiscoveryClient",
    "FederationDiscoveryError",
    "FederationDeliveryTarget",
    "FederationDeadLetterEvent",
    "FederationHTTPResponse",
    "FederationHostRejected",
    "FederationKeyError",
    "FederationManifestError",
    "FederationPrivateKey",
    "FederationSignatureError",
    "FederationTransportError",
    "FederationUnknownKey",
    "InboundFederationReceipt",
    "MessageDeliveryPlan",
    "MessageDeliveryTarget",
    "OutboundFederationDelivery",
    "OutboundFederationService",
    "ResolvedFederationKey",
    "SignedFederationRequest",
    "VerifiedFederationSignature",
    "FederationWorker",
    "HTTPFederationTransport",
    "build_bounce_delivery",
    "build_federation_bounces",
    "build_message_delivery_plan",
    "public_key_from_manifest",
    "classify_http_status",
    "is_dsn",
    "load_federation_private_key",
    "parse_retry_after",
    "retry_delay_for_attempt",
    "serialize_federation_envelope",
    "sign_federation_request",
    "verify_federation_request",
    "verify_federation_request_with_discovery",
]
