# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

import re
import uuid

import validators

from mail_protocol.core.constants import (
    AGENT_NAME_LEN_MAX,
    AGENT_NAME_LEN_MIN,
    DAEMON_WORKER_NAME_LEN_MAX,
    DAEMON_WORKER_NAME_LEN_MIN,
    MESSAGE_BODY_LEN_MAX,
    MESSAGE_BODY_LEN_MIN,
    MESSAGE_SUBJECT_LEN_MAX,
    MESSAGE_SUBJECT_LEN_MIN,
    SWARM_DESCRIPTION_LEN_MAX,
    SWARM_DESCRIPTION_LEN_MIN,
    SWARM_KEYWORD_LEN_MAX,
    SWARM_KEYWORD_LEN_MIN,
    SWARM_NAME_LEN_MAX,
    SWARM_NAME_LEN_MIN,
    USER_NAME_LEN_MAX,
    USER_NAME_LEN_MIN,
)


def validate_uuid(string: str) -> str:
    """
    Ensure that the given string is a valid UUID.
    """

    try:
        _result = uuid.UUID(string)
    except Exception as e:
        raise ValueError(f"UUID parsing failed for {string}: {e}")

    return string


def validate_uuids(strings: list[str]) -> list[str]:
    """
    Ensure that the given list of strings is a valid list of UUIDs.
    """

    for string in strings:
        validate_uuid(string)

    return strings


def validate_message_subject(subject: str) -> str:
    """
    Ensure that the given string is a valid MAIL message subject.
    """

    subject_len = len(subject)
    if subject_len < MESSAGE_SUBJECT_LEN_MIN:
        raise ValueError(
            f"message subject must be at least {MESSAGE_SUBJECT_LEN_MIN} characters long"
        )
    if subject_len > MESSAGE_SUBJECT_LEN_MAX:
        raise ValueError(
            f"message subject must be no longer than {MESSAGE_SUBJECT_LEN_MAX} characters"
        )

    return subject


def validate_message_body(body: str) -> str:
    """
    Ensure that the given string is a valid MAIL message body.
    """

    body_len = len(body)
    if body_len < MESSAGE_BODY_LEN_MIN:
        raise ValueError(
            f"message body must be at least {MESSAGE_BODY_LEN_MIN} characters long"
        )
    if body_len > MESSAGE_BODY_LEN_MAX:
        raise ValueError(
            f"message body must be no longer than {MESSAGE_BODY_LEN_MAX} characters"
        )

    return body


def validate_mail_address(address: str) -> str:
    """
    Ensure that the given string is a valid MAIL address.
    """

    at_split = address.split("@")

    if len(at_split) == 3:
        # TODO: handle agent addresses
        agent_name, swarm_name, host = at_split
        validate_agent_name(agent_name)
        validate_swarm_name(swarm_name)
        validate_host(host)

    elif len(at_split) == 2:
        # TODO: handle admin/user/daemon addresses
        prefix, host = at_split
        colon_split = prefix.split(":")
        if len(colon_split) != 2:
            raise ValueError("invalid MAIL address structure")
        ua_type, ua_id = colon_split
        match ua_type:
            case "user" | "admin":
                validate_user_name(ua_id)
            case "daemon":
                validate_daemon_worker_name(ua_id)
            case _:
                raise ValueError(f"invalid MAIL user-agent type: {ua_type}")
        validate_host(host)

    else:
        raise ValueError("invalid MAIL address structure")

    return address


def validate_mail_addresses(addresses: list[str]) -> list[str]:
    """
    Ensure that all address strings provided are valid MAIL addresses.
    """

    for addr in addresses:
        validate_mail_address(addr)

    return addresses


def validate_agent_name(name: str) -> str:
    """
    Ensure that the given string is a valid agent name.
    """

    name_len = len(name)
    if name_len < AGENT_NAME_LEN_MIN:
        raise ValueError(
            f"agent name must be at least {AGENT_NAME_LEN_MIN} characters long"
        )
    if name_len > AGENT_NAME_LEN_MAX:
        raise ValueError(
            f"agent name must be no longer than {AGENT_NAME_LEN_MAX} characters"
        )
    if not string_is_slug(name):
        raise ValueError(f"invalid slug string: {name}")

    return name


def validate_agent_names(names: list[str]) -> list[str]:
    """
    Ensure that all strings provided are valid MAIL agent names.
    """

    for name in names:
        validate_agent_name(name)

    return names


def validate_user_name(name: str) -> str:
    """
    Ensure that the string provided is a valid MAIL user/admin name.
    """

    name_len = len(name)
    if name_len < USER_NAME_LEN_MIN:
        raise ValueError(
            f"user name must be at least {USER_NAME_LEN_MIN} characters long"
        )
    if name_len > USER_NAME_LEN_MAX:
        raise ValueError(
            f"user name must be no longer than {USER_NAME_LEN_MAX} characters"
        )
    if not string_is_slug(name):
        raise ValueError(f"invalid slug string: {name}")

    return name


def validate_user_names(names: list[str]) -> list[str]:
    """
    Ensure all strings provided are valid MAIL user/admin names.
    """

    for name in names:
        validate_user_name(name)

    return names


def validate_swarm_name(name: str) -> str:
    """
    Ensure that the given string is a valid swarm name.
    """

    name_len = len(name)
    if name_len < SWARM_NAME_LEN_MIN:
        raise ValueError(
            f"swarm name must be at least {SWARM_NAME_LEN_MIN} characters long"
        )
    if name_len > SWARM_NAME_LEN_MAX:
        raise ValueError(
            f"swarm name must be no longer than {SWARM_NAME_LEN_MAX} characters"
        )
    if not string_is_slug(name):
        raise ValueError(f"invalid slug string: {name}")

    return name


def validate_swarm_description(description: str) -> str:
    """
    Ensure that the given string is a valid swarm description.
    """

    desc_len = len(description)
    if desc_len < SWARM_DESCRIPTION_LEN_MIN:
        raise ValueError(
            f"swarm description must be at least {SWARM_DESCRIPTION_LEN_MIN} characters long"
        )
    if desc_len > SWARM_DESCRIPTION_LEN_MAX:
        raise ValueError(
            f"swarm description must be no longer than {SWARM_NAME_LEN_MAX} characters"
        )

    return description


def validate_swarm_keyword(keyword: str) -> str:
    """
    Ensure that the given string is a valid MAIL swarm keyword.
    """

    kw_len = len(keyword)
    if kw_len < SWARM_KEYWORD_LEN_MIN:
        raise ValueError(
            f"swarm keyword must be at least {SWARM_KEYWORD_LEN_MIN} characters long"
        )
    if kw_len > SWARM_KEYWORD_LEN_MAX:
        raise ValueError(
            f"swarm keyword must be no longer than {SWARM_KEYWORD_LEN_MAX} characters"
        )
    if not string_is_slug(keyword):
        raise ValueError(f"invalid slug string: {keyword}")

    return keyword


def validate_swarm_keywords(keywords: list[str]) -> list[str]:
    """
    Ensure that all strings provided are valid MAIL swarm keywords.
    """

    for keyword in keywords:
        validate_swarm_keyword(keyword)

    return keywords


def validate_host(host: str) -> str:
    """
    Ensure that the given string is a valid MAIL server host name.
    """

    if validators.hostname(host):
        return host
    elif validators.ipv4(host):
        return host
    elif validators.ipv6(host):
        return host
    else:
        raise ValueError(f"{host} is not a valid hostname or IP address")


def validate_daemon_worker_name(name: str) -> str:
    """
    Ensure that the given stirng is a valid MAIL daemon worker name.
    """

    name_len = len(name)
    if name_len < DAEMON_WORKER_NAME_LEN_MIN:
        raise ValueError(
            f"daemon worker name must be at least {DAEMON_WORKER_NAME_LEN_MIN} characters long"
        )
    if name_len > DAEMON_WORKER_NAME_LEN_MAX:
        raise ValueError(
            f"daemon worker name must be no longer than {DAEMON_WORKER_NAME_LEN_MAX} characters"
        )
    if not string_is_slug(name):
        raise ValueError(f"invalid slug string: {name}")

    return name


def validate_daemon_worker_names(names: list[str]) -> list[str]:
    """
    Ensure that all given strings are valid MAIL daemon worker names.
    """

    for name in names:
        validate_daemon_worker_name(name)

    return names


def string_is_slug(string: str) -> bool:
    """
    Check if the given string is a valid slug.
    """

    pattern = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    return bool(re.match(pattern, string))
