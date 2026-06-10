# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

DEFAULT_OUTPUT = Path("spec/openapi.yaml")


def _set_import_defaults() -> None:
    """
    mail-server reads these values while modules are imported. Generation only
    needs the FastAPI route metadata, so deterministic local placeholders are
    sufficient.
    """

    os.environ.setdefault("MAIL_HOST", "localhost")
    os.environ.setdefault("MAIL_JWT_SECRET_KEY", "openapi-generation-only")
    os.environ.setdefault("MAIL_JWT_ALGORITHM", "HS256")
    os.environ.setdefault("MAIL_JWT_EXPIRE_MINUTES", "15")


def _load_schema() -> dict[str, Any]:
    _set_import_defaults()

    from mail_server.server import app

    return app.openapi()


def _write_json(schema: dict[str, Any], output_path: Path) -> None:
    output_path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")


def _write_yaml(schema: dict[str, Any], output_path: Path) -> None:
    try:
        import yaml
    except ImportError as exc:
        raise SystemExit(
            "PyYAML is required for YAML output. Use --output spec/openapi.json "
            "or install PyYAML."
        ) from exc

    output_path.write_text(
        yaml.safe_dump(schema, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def write_schema(schema: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = output_path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        _write_yaml(schema, output_path)
        return
    if suffix == ".json":
        _write_json(schema, output_path)
        return
    raise SystemExit("Output path must end with .yaml, .yml, or .json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate OpenAPI from the current mail-server FastAPI app.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"path to write the generated schema (default: {DEFAULT_OUTPUT})",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    schema = _load_schema()
    write_schema(schema=schema, output_path=args.output)
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
