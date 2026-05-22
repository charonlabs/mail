# SPDX-Licence-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

import logging
from argparse import Namespace
from os import getenv
from time import sleep

import httpx
from mail_protocol.core.messages import MAILMessage
from mail_protocol.network.requests import PostDaemonDeliverLocalRequest
from mail_protocol.network.responses import (
    GetAuthWhoamiResponse,
    GetRootResponse,
    PostAuthTokenResponse,
    PostDaemonDeliverLocalResponse,
    PostDaemonMessageBufferClearResponse,
)
from pydantic import ValidationError

logger = logging.getLogger("maild")

_mail_server: str = None  # type: ignore
_mail_address: str = None  # type: ignore
_mail_password: str = None  # type: ignore
_mail_token: str = None  # type: ignore


def run_daemon(args: Namespace) -> None:
    """
    Run the mail-daemon from the CLI.
    """

    logger.info("daemon starting up...")

    try:
        _check_env_vars()
    except ValueError as e:
        raise ValueError(f"missing required environment variable: {e}")

    try:
        _check_server()
    except RuntimeError:
        raise
    except ValueError as e:
        raise ValueError(f"MAIL protocol error: {e}")

    try:
        _obtain_daemon_token()
    except RuntimeError:
        raise
    except ValueError as e:
        raise ValueError(f"response error: {e}")

    daemon_loop()

    logger.info("daemon shutdown complete")


def daemon_loop(sleep_seconds: int = 30) -> None:
    """
    Run the core daemon loop.
    sleep_seconds (int): The number of seconds to pause between iterations
    """

    logger.info("starting daemon loop...")

    try:
        while True:
            message_ids = clear_message_buffer()
            deliver_messages(message_ids)
            sleep(sleep_seconds)

    except KeyboardInterrupt:
        logger.info("daemon loop stopped")


def clear_message_buffer() -> list[str]:
    """
    Obtain all messages in the server's delivery buffer.
    """
    global _mail_server, _mail_token
    logger.debug(f"getting server message buffer: {_mail_server}...")
    try:
        response = httpx.post(
            url=f"{_mail_server}/daemon/message-buffer/clear",
            headers={
                "User-Agent": "Multi-Agent-Interface-Layer-Daemon/2.0.0 (github.com/charonlabs/mail)",
                "Authorization": f"Bearer {_mail_token}",
            },
        )
    except Exception as e:
        logger.error(f"message buffer clear request failed: {e}")
        return []

    if response.status_code != 200:
        logger.warning(
            f"message buffer clear request to {_mail_server} got non-200 status code: {response.status_code}"
        )
        return []

    try:
        response_obj = PostDaemonMessageBufferClearResponse.model_validate(
            response.json()
        )
    except ValidationError as e:
        logger.error(
            f"message buffer clear response from {_mail_server} failed validation: {e}"
        )
        return []

    return response_obj.message_ids


def deliver_messages(message_ids: list[str]) -> None:
    """
    Attempt to deliver the messages fetched from the server buffer.
    """

    payload = PostDaemonDeliverLocalRequest(
        message_ids=message_ids,
    )

    global _mail_server, _mail_token
    logger.debug(f"delivering local messages: {_mail_server}...")
    try:
        response = httpx.post(
            url=f"{_mail_server}/daemon/deliver/local",
            headers={
                "User-Agent": "Multi-Agent-Interface-Layer-Daemon/2.0.0 (github.com/charonlabs/mail)",
                "Authorization": f"Bearer {_mail_token}",
                "Content-Type": "application/json",
            },
            json=payload.model_dump(),
        )
    except Exception as e:
        logger.error(f"message local delivery request failed: {e}")
        return

    if response.status_code != 200:
        logger.warning(
            f"message local delivery request to {_mail_server} got non-200 status code: {response.status_code}"
        )
        return

    try:
        response_obj = PostDaemonDeliverLocalResponse.model_validate(response.json())
    except ValidationError as e:
        logger.error(
            f"message local delivery response from {_mail_server} failed validation: {e}"
        )
        return

    num_sent = len(message_ids)
    num_delivered = len(response_obj.messages)
    if num_sent != num_delivered:
        logger.warning(
            f"mismatch: daemon sent {num_sent} messages, server sent {num_delivered}"
        )


def _check_env_vars() -> None:
    """
    Ensure the required environment variables are present.
    """

    logger.info("checking env vars...")

    MAIL_SERVER = getenv("MAIL_SERVER")
    if MAIL_SERVER is None:
        logger.critical("env var MAIL_SERVER is not set!")
        raise ValueError("MAIL_SERVER is not set")
    MAIL_ADDRESS = getenv("MAIL_ADDRESS")
    if MAIL_ADDRESS is None:
        logger.critical("env var MAIL_ADDRESS is not set!")
        raise ValueError("MAIL_ADDRESS is not set")
    MAIL_PASSWORD = getenv("MAIL_PASSWORD")
    if MAIL_PASSWORD is None:
        logger.critical("env var MAIL_PASSWORD is not set!")
        raise ValueError("MAIL_PASSWORD is not set")

    global _mail_server, _mail_address, _mail_password
    _mail_server = MAIL_SERVER
    _mail_address = MAIL_ADDRESS
    _mail_password = MAIL_PASSWORD

    logger.info("all required env vars found")


def _check_server() -> None:
    """
    Ensure that the provided env var MAIL_SERVER points to a valid MAIL server.
    """

    logger.info("checking MAIL_SERVER...")

    global _mail_server
    try:
        response = httpx.get(
            url=_mail_server,
            headers={
                "User-Agent": "Multi-Agent-Interface-Layer-Daemon/2.0.0 (github.com/charonlabs/mail)"
            },
        )
    except Exception as e:
        logger.critical(f"request to MAIL_SERVER failed: {e}")
        raise RuntimeError(f"request to MAIL_SERVER failed: {e}")

    if response.status_code != 200:
        logger.critical(
            f"response from {_mail_server} got non-200 status code: {response.status_code}"
        )
        raise RuntimeError(
            f"response from {_mail_server} got non-200 status code: {response.status_code}"
        )

    try:
        _get_root_response = GetRootResponse.model_validate(response.json())
    except ValidationError as e:
        logger.critical(f"got unexpected response from `GET /`: {e}")
        raise ValueError(f"got unexpected response from `GET /`: {e}")

    logger.info("MAIL_SERVER deemed valid")


def _obtain_daemon_token() -> None:
    """
    Attempt to log into the MAIL server with the provided credentials as a daemon.
    """

    logger.info("obtaining daemon token...")

    global _mail_address, _mail_password
    payload = {
        "grant_type": "password",
        "username": _mail_address,
        "password": _mail_password,
        "scope": "",
        "client_id": "string",
        "client_secret": "$password",
    }

    # 1. attempt to log into the MAIL server
    global _mail_server
    try:
        response_login = httpx.post(
            url=f"{_mail_server}/auth/token",
            headers={
                "accept": "application/json",
                "User-Agent": "Multi-Agent-Interface-Layer-Daemon/2.0.0 (github.com/charonlabs/mail)",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data=payload,
        )
    except Exception as e:
        logger.critical(f"login request to MAIL_SERVER failed: {e}")
        raise RuntimeError(f"login request to MAIL_SERVER failed: {e}")

    if response_login.status_code != 200:
        logger.critical(
            f"response from {_mail_server} got non-200 status code: {response_login.status_code}"
        )
        raise RuntimeError(
            f"response from {_mail_server} got non-200 status code: {response_login.status_code}"
        )

    try:
        post_token_response = PostAuthTokenResponse.model_validate(
            response_login.json()
        )
    except ValidationError as e:
        logger.critical(f"got unexpected response from `POST /auth/token`: {e}")
        raise ValueError(f"got unexpected response from `POST /auth/token`: {e}")

    token = post_token_response.access_token

    # 2. ensure that the returned token is a valid MAIL daemon token
    try:
        response_whoami = httpx.get(
            url=f"{_mail_server}/auth/whoami",
            headers={
                "User-Agent": "Multi-Agent-Interface-Layer-Daemon/2.0.0 (github.com/charonlabs/mail)",
                "Authorization": f"Bearer {token}",
            },
        )
    except Exception as e:
        logger.critical(f"whoami request to MAIL_SERVER failed: {e}")
        raise RuntimeError(f"whoami request to MAIL_SERVER failed: {e}")

    if response_whoami.status_code != 200:
        logger.critical(
            f"response from {_mail_server} got non-200 status code: {response_whoami.status_code}"
        )
        raise RuntimeError(
            f"response from {_mail_server} got non-200 status code: {response_whoami.status_code}"
        )

    try:
        get_whoami_response = GetAuthWhoamiResponse.model_validate(
            response_whoami.json()
        )
    except ValidationError as e:
        logger.critical(f"got unexpected response from `GET /auth/whoami`: {e}")
        raise ValueError(f"got unexpected response from `GET /auth/whoami`: {e}")

    user_agent = get_whoami_response.user_agent.user_agent
    if user_agent.ua_type != "daemon":
        logger.critical(f"got unexpected MAIL user-agent type: {user_agent.ua_type}")
        raise ValueError(f"got unexpected MAIL user-agent type: {user_agent.ua_type}")

    # we can now consider ourselves logged in
    global _mail_token
    _mail_token = token

    logger.info("daemon token deemed valid")
