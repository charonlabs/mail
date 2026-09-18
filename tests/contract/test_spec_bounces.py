# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs

"""SPEC.md §8.4 delivery status notification data-contract conformance."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from mail_protocol.core.dsn import MAILDSN
from pydantic import ValidationError


def make_dsn(**overrides: Any) -> MAILDSN:
    fields: dict[str, Any] = {
        "failure_code": "recipient_not_found",
        "failure_reason": "recipient not found",
        "original_message_id": "55555555-5555-4555-8555-555555555555",
        "failed_recipient": "ghost@village@server-b.example.com",
        "failed_at": "destination",
        "timestamp": datetime(2026, 9, 14, 18, 0, tzinfo=UTC),
    }
    fields.update(overrides)
    return MAILDSN(**fields)


def test_local_dsn_omits_attempt_fields() -> None:
    """§8.4: local failures have no retry-attempt metadata."""

    dsn = make_dsn(failed_recipient="user:ghost@server-a.example.com")
    assert dsn.attempt_count is None
    assert dsn.attempt_timestamps is None


def test_in_transit_dsn_requires_attempt_count() -> None:
    """§8.4: every in-transit failure is a federation failure."""

    with pytest.raises(ValidationError):
        make_dsn(
            failure_code="host_unreachable",
            failed_at="in_transit",
        )
    dsn = make_dsn(
        failure_code="host_unreachable",
        failed_at="in_transit",
        attempt_count=6,
    )
    assert dsn.attempt_count == 6


def test_origin_failure_must_not_carry_attempt_fields() -> None:
    """§8.4: origin/local failures omit federation attempt metadata."""

    with pytest.raises(ValidationError):
        make_dsn(
            failure_code="internal_error",
            failed_at="origin",
            attempt_count=1,
        )


def test_destination_failure_may_identify_a_federation_attempt() -> None:
    """§8.4: federation's immediate permanent peer rejection is attempt 1."""

    dsn = make_dsn(
        failure_code="policy_denied",
        failed_at="destination",
        attempt_count=1,
    )
    assert dsn.attempt_count == 1


def test_attempt_timestamps_match_count_and_are_oldest_first() -> None:
    """§8.4: optional attempt timestamps are complete and ordered."""

    first = datetime(2026, 9, 14, 18, 0, tzinfo=UTC)
    second = first + timedelta(seconds=1)
    dsn = make_dsn(
        failure_code="delivery_expired",
        failed_at="in_transit",
        attempt_count=2,
        attempt_timestamps=[first, second],
    )
    assert dsn.attempt_timestamps == [first, second]

    with pytest.raises(ValidationError):
        make_dsn(
            failure_code="delivery_expired",
            failed_at="in_transit",
            attempt_count=2,
            attempt_timestamps=[first],
        )
    with pytest.raises(ValidationError):
        make_dsn(
            failure_code="delivery_expired",
            failed_at="in_transit",
            attempt_count=2,
            attempt_timestamps=[second, first],
        )


def test_attempt_timestamps_require_attempt_count() -> None:
    with pytest.raises(ValidationError):
        make_dsn(attempt_timestamps=[datetime(2026, 9, 14, 18, 0, tzinfo=UTC)])


def test_dsn_timestamps_must_be_timezone_aware() -> None:
    with pytest.raises(ValidationError):
        make_dsn(timestamp=datetime(2026, 9, 14, 18, 0))
    with pytest.raises(ValidationError):
        make_dsn(
            failure_code="delivery_expired",
            failed_at="in_transit",
            attempt_count=1,
            attempt_timestamps=[datetime(2026, 9, 14, 18, 0)],
        )


def test_unknown_future_failure_code_is_accepted() -> None:
    """§8.4: clients render the reason for failure-code extensions."""

    assert make_dsn(failure_code="future_failure").failure_code == "future_failure"


@pytest.mark.parametrize(
    "overrides",
    [
        {"failure_reason": ""},
        {"original_message_id": "not-a-uuid"},
        {"failed_recipient": "not-an-address"},
        {"attempt_count": 0},
    ],
)
def test_dsn_rejects_malformed_required_fields(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        make_dsn(**overrides)


def test_dsn_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        MAILDSN(**make_dsn().model_dump(), retryable=False)
