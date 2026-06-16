#!/usr/bin/env python3
"""Bump every MAIL package to a new version, in lockstep.

MAIL ships five distributions from one uv workspace that share a single
version and pin each other exactly (`mail-client==X`, ...). This script keeps
them in sync so a release can never go out half-bumped.

Usage:
    python scripts/bump-version.py 2.0.1
    python scripts/bump-version.py --check        # verify all five already agree

It rewrites, in every pyproject.toml:
  * the package's own `version = "..."`
  * any exact internal pin `"mail-<member>==..."`
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

PYPROJECTS = [
    ROOT / "pyproject.toml",
    ROOT / "src" / "mail" / "client" / "pyproject.toml",
    ROOT / "src" / "mail" / "server" / "pyproject.toml",
    ROOT / "src" / "mail" / "daemon" / "pyproject.toml",
    ROOT / "src" / "mail" / "protocol" / "pyproject.toml",
]

# PEP 440-ish: release plus optional pre/post/dev suffix (e.g. 2.0.1, 2.1.0rc1).
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:(?:a|b|rc)\d+|\.post\d+|\.dev\d+)?$")

_VERSION_LINE = re.compile(r'^version = "[^"]+"$', re.MULTILINE)
# Any version specifier on an internal member pin is normalized to `==<version>`.
# Scoped to the four member names, so external deps (e.g. dict2xml>=…) are untouched.
_INTERNAL_PIN = re.compile(
    r'"(mail-swarms-(?:client|server|daemon|protocol))(?:==|>=|~=|!=|===|>|<)[^"]*"')


def current_version(text: str) -> str | None:
    m = re.search(r'^version = "([^"]+)"$', text, re.MULTILINE)
    return m.group(1) if m else None


def check() -> int:
    versions = {p: current_version(p.read_text()) for p in PYPROJECTS}
    unique = set(versions.values())
    for p, v in versions.items():
        print(f"  {v}\t{p.relative_to(ROOT)}")
    if len(unique) != 1 or None in unique:
        print("ERROR: package versions are not in lockstep", file=sys.stderr)
        return 1
    print(f"OK: all packages at {unique.pop()}")
    return 0


def bump(version: str) -> int:
    if not VERSION_RE.match(version):
        print(f"ERROR: '{version}' is not a valid version", file=sys.stderr)
        return 2
    for p in PYPROJECTS:
        text = p.read_text()
        text = _VERSION_LINE.sub(f'version = "{version}"', text, count=1)
        text = _INTERNAL_PIN.sub(rf'"\1=={version}"', text)
        p.write_text(text)
        print(f"  bumped {p.relative_to(ROOT)} -> {version}")
    print(f"\nAll packages set to {version}. Next: commit, tag v{version}, "
          f"then publish the GitHub Release as a full (non-prerelease) release.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("version", nargs="?", help="new version, e.g. 2.0.1")
    g.add_argument("--check", action="store_true",
                   help="verify all packages already share one version")
    args = ap.parse_args()
    return check() if args.check else bump(args.version)


if __name__ == "__main__":
    raise SystemExit(main())
