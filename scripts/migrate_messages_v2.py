# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

"""
Migrate persisted ``MAILMessage`` records to the MAIL 2.0 schema.

MAIL 2.0 adds two required fields to ``MAILMessage``:

* ``mail_version`` (``"2.0"``)
* ``tags`` (a list of slug strings; empty by default)

Messages persisted before these fields existed will fail
``MAILMessage.model_validate_json()`` on server startup and be silently
dropped by the memory backend's loader. This script walks a deployment's
``messages/`` directory and backfills the two new fields on any record that
is missing them, so an upgrade does not lose existing messages.

The optional ``reply_to`` field has a default of ``None`` and therefore needs
no migration.

Usage::

    # preview changes for the default deployment
    uv run python scripts/migrate_messages_v2.py --dry-run

    # migrate the default deployment in place (a backup is taken first)
    uv run python scripts/migrate_messages_v2.py

    # migrate a named deployment, or an explicit messages directory
    uv run python scripts/migrate_messages_v2.py --deployment my-deployment
    uv run python scripts/migrate_messages_v2.py --messages-dir /path/to/messages
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

MAIL_VERSION = "2.0"

DEFAULT_DEPLOYMENTS_ROOT = Path.home().joinpath(".mail-swarms", "deployments")


@dataclass
class MigrationResult:
    """Summary of a migration run."""

    scanned: int = 0
    migrated: int = 0
    already_current: int = 0
    skipped: list[str] = field(default_factory=list)


def _atomic_write_text(path: Path, content: str) -> None:
    """
    Atomically replace ``path`` with ``content`` (temp file + ``os.replace``).
    Mirrors the memory backend's persistence write so the on-disk format and
    durability guarantees match.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            tmp_file.write(content)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        os.replace(tmp_path, path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _needs_migration(record: dict) -> bool:
    return "mail_version" not in record or "tags" not in record


def _upgrade_record(record: dict) -> dict:
    """
    Return ``record`` with the MAIL 2.0 fields backfilled. Existing values are
    left untouched; only missing fields are added.
    """

    if "mail_version" not in record:
        record["mail_version"] = MAIL_VERSION
    if "tags" not in record:
        record["tags"] = []
    return record


def migrate_messages(messages_dir: Path, *, dry_run: bool = False) -> MigrationResult:
    """
    Backfill MAIL 2.0 fields on every message file in ``messages_dir``.

    Files are read as raw JSON (the model is intentionally bypassed so that
    pre-2.0 records can be loaded at all). Records missing ``mail_version`` or
    ``tags`` are rewritten in place; records that already have both are left
    untouched. Files that are not valid JSON objects are reported as skipped.
    """

    result = MigrationResult()
    if not messages_dir.is_dir():
        raise FileNotFoundError(f"messages directory not found: {messages_dir}")

    for entry in sorted(messages_dir.iterdir()):
        if not entry.is_file():
            continue
        result.scanned += 1

        try:
            record = json.loads(entry.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            result.skipped.append(f"{entry.name}: unreadable ({e})")
            continue

        if not isinstance(record, dict):
            result.skipped.append(f"{entry.name}: not a JSON object")
            continue

        if not _needs_migration(record):
            result.already_current += 1
            continue

        result.migrated += 1
        if dry_run:
            continue

        upgraded = _upgrade_record(record)
        _atomic_write_text(entry, json.dumps(upgraded))

    return result


def _resolve_messages_dir(args: argparse.Namespace) -> Path:
    if args.messages_dir is not None:
        return Path(args.messages_dir)
    return Path(args.root).joinpath(args.deployment, "messages")


def _backup_dir(messages_dir: Path) -> Path:
    backup = messages_dir.with_name(f"{messages_dir.name}.backup")
    if backup.exists():
        raise FileExistsError(
            f"backup already exists: {backup} (remove or rename it first)"
        )
    shutil.copytree(messages_dir, backup)
    return backup


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Migrate persisted MAILMessage records to the MAIL 2.0 schema."
    )
    parser.add_argument(
        "--deployment",
        default="default",
        help="deployment name under the deployments root (default: %(default)s)",
    )
    parser.add_argument(
        "--root",
        default=str(DEFAULT_DEPLOYMENTS_ROOT),
        help="deployments root directory (default: %(default)s)",
    )
    parser.add_argument(
        "--messages-dir",
        default=None,
        help="explicit path to a messages/ directory (overrides --deployment/--root)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would change without modifying any files",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="skip copying the messages directory to <messages>.backup before migrating",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    messages_dir = _resolve_messages_dir(args)

    print(f"=== MAIL 2.0 message migration: {messages_dir} ===")
    if not messages_dir.is_dir():
        print(f"❌ messages directory not found: {messages_dir}")
        sys.exit(1)

    if args.dry_run:
        result = migrate_messages(messages_dir, dry_run=True)
        print("🔍 DRY RUN — no files were modified")
    else:
        # Probe first so we only take a backup when there is work to do.
        preview = migrate_messages(messages_dir, dry_run=True)
        if preview.migrated and not args.no_backup:
            backup = _backup_dir(messages_dir)
            print(f"✅ backed up {preview.scanned} files to {backup}")
        result = migrate_messages(messages_dir, dry_run=False)

    print(f"scanned:         {result.scanned}")
    print(f"migrated:        {result.migrated}")
    print(f"already current: {result.already_current}")
    if result.skipped:
        print(f"skipped:         {len(result.skipped)}")
        for note in result.skipped:
            print(f"  - {note}")

    print("🎉 migration complete")


if __name__ == "__main__":
    main()
