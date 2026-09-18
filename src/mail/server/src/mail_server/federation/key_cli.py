# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""Operator CLI for generating and inspecting Federation v1 signing keys."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from mail_protocol.cli_help import make_arg_parser

from mail_server.federation.keys import (
    FederationKeyError,
    FederationPrivateKey,
    generate_federation_private_key,
    load_federation_private_key,
)


def build_parser() -> argparse.ArgumentParser:
    parser = make_arg_parser(
        prog="mail-federation-key",
        usage="mail-federation-key {generate,inspect} [option]...",
        description="Generate or inspect a MAIL Federation v1 Ed25519 key",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("generate", "inspect"):
        command_parser = subparsers.add_parser(
            command,
            help=f"{command} a federation signing key",
        )
        command_parser.add_argument(
            "path",
            type=Path,
            help="path to the unencrypted Ed25519 private-key PEM",
        )
        command_parser.add_argument(
            "--key-id",
            required=True,
            help="public key identifier advertised in the federation manifest",
        )
        command_parser.add_argument(
            "--json",
            action="store_true",
            help="print the public key record as JSON",
        )
    return parser


def _print_key(key: FederationPrivateKey, *, path: Path, json_output: bool) -> None:
    public = key.manifest_key()
    if json_output:
        print(public.model_dump_json())
        return
    print(f"Private Key File: {path}")
    print(f"Key ID: {public.key_id}")
    print(f"Algorithm: {public.algorithm}")
    print(f"Public Key: {public.public_key}")


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            key = generate_federation_private_key(args.path, key_id=args.key_id)
        else:
            key = load_federation_private_key(args.path, key_id=args.key_id)
    except FederationKeyError as exc:
        parser.error(str(exc))
    _print_key(key, path=args.path, json_output=args.json)
