#!/usr/bin/env python3

# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from __future__ import annotations

import argparse
import logging
import sys
import textwrap
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path

DEFAULT_LOCK_PATH = Path("uv.lock")
DEFAULT_OUTPUT_PATH = Path("THIRD_PARTY_NOTICES.md")

COMMON_LICENSE_BASENAMES = (
    "LICENSE",
    "LICENSE.txt",
    "LICENSE.md",
    "LICENSE.rst",
    "LICENSE-APACHE",
    "LICENSE-MIT",
    "LICENCE",
    "LICENCE.txt",
    "LICENCE.md",
    "COPYING",
    "COPYING.txt",
    "COPYING.md",
    "NOTICE",
    "NOTICE.txt",
    "NOTICE.md",
)

LICENSE_KEYWORDS = ("license", "licence", "copying", "notice", "copyright")


@dataclass
class PackageReport:
    """
    A container of metadata about a third-party package.
    Ideally contains all relevant license information.
    """

    name: str
    version: str
    summary: str | None = None
    license: str | None = None
    license_classifiers: list[str] = field(default_factory=list)
    home_page: str | None = None
    author: str | None = None
    license_texts: list[tuple[str, str]] = field(default_factory=list)
    infos: list[str] = field(default_factory=list)  # log level `INFO`
    warnings: list[str] = field(default_factory=list)  # log level `WARNING`


def load_packages(lock_path: Path) -> dict[str, str]:
    """
    Load the packages from the `uv.lock` file.
    """
    data = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    packages = {}

    for entry in data.get("package", []):
        name = entry.get("name")
        version = entry.get("version")
        if not name or not version:
            continue
        packages[name] = version

    return packages


def pick_license_texts(dist: metadata.Distribution) -> list[str]:
    """
    Pick the license texts from the distribution.
    """
    meta = dist.metadata
    results: list[str] = []
    seen: set[str] = set()

    def add_candidate(value: str | None) -> None:
        if not value:
            return
        normalized = value.strip()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        results.append(normalized)

    for declared in meta.get_all("License-File") or []:
        add_candidate(str(declared))

    files = dist.files or []
    if files:
        preferred_names = {name.lower() for name in COMMON_LICENSE_BASENAMES}
        for file in files:
            file_name = getattr(file, "name", None)
            if file_name and file_name.lower() in preferred_names:
                add_candidate(str(file))
        if not results:
            for file in files:
                normalized = str(file).lower()
                if any(keyword in normalized for keyword in LICENSE_KEYWORDS):
                    add_candidate(str(file))

    if not results:
        for candidate in COMMON_LICENSE_BASENAMES:
            try:
                located = dist.locate_file(candidate)
            except FileNotFoundError:
                continue
            path_obj = Path(str(located))
            if path_obj.exists() and path_obj.is_file():
                add_candidate(candidate)

    return results


def read_license_file(dist: metadata.Distribution, relative_path: str) -> str | None:
    """
    Attempt to read the license file from a distribution and return its contents.
    """
    try:
        content = dist.read_text(relative_path)
        if content is not None:
            return content
    except FileNotFoundError:
        pass

    try:
        file_path = dist.locate_file(relative_path)
    except FileNotFoundError:
        return None

    path_obj = Path(str(file_path))
    if not path_obj.exists():
        return None

    return path_obj.read_text(encoding="utf-8", errors="replace")


def build_report(name: str, version: str) -> PackageReport:
    """
    Build a `PackageReport` for a third-party package given its name and version.
    """
    report = PackageReport(name=name, version=version)

    try:
        dist = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        report.warnings.append("Package not installed; install to capture metadata.")
        return report

    meta = dist.metadata
    report.summary = meta.get("Summary")
    license_expression = meta.get("License-Expression")
    if license_expression:
        report.license = license_expression.strip() or None
    else:
        legacy_license = meta.get("License")
        if legacy_license:
            cleaned = legacy_license.strip()
            if cleaned and cleaned.upper() != "UNKNOWN":
                report.license = cleaned
    report.license_classifiers = meta.get_all("Classifier") or []
    if not report.license:
        classifier_hint = next(
            (cls for cls in report.license_classifiers if cls.startswith("License ::")),
            None,
        )
        if classifier_hint:
            report.license = classifier_hint.split("::")[-1].strip()
    report.home_page = meta.get("Home-page")
    report.author = meta.get("Author")

    for rel_path in pick_license_texts(dist):
        text = read_license_file(dist, rel_path)
        if text:
            report.license_texts.append((rel_path, text))
        else:
            report.infos.append(f"Unable to read license file: {rel_path}")

    if not report.license and not report.license_texts:
        report.warnings.append("No license metadata discovered; manual review needed.")

    return report


def format_classifier_summary(classifiers: Iterable[str]) -> list[str]:
    """
    Format license classifiers into a summary list.
    """
    results = []

    for classifier in classifiers:
        if classifier.startswith("License ::"):
            results.append(classifier)

    return results


def write_output(reports: Iterable[PackageReport], output_path: Path) -> None:
    """
    Write the reports to a file.
    """
    header = textwrap.dedent(
        """
        # Third-Party Notices

        _Generated by [scripts/build_third_party_licenses.py](/scripts/build_third_party_licenses.py). 
        Ensure all listed packages remain installed when re-running 
        so their license metadata stays accessible._
        """
    ).strip()

    lines: list[str] = [header, ""]

    for report in sorted(reports, key=lambda r: r.name.lower()):
        title = f"## `{report.name}=={report.version}`"
        lines.append(title)

        if report.summary:
            lines.append(f"{report.summary}")
        license_line = report.license or "(license metadata not found)"
        lines.append(f"### License field:\n{license_line}")

        classifiers = format_classifier_summary(report.license_classifiers)
        if classifiers:
            lines.append("### Classifiers:\n" + "; ".join(classifiers))
        if report.home_page:
            lines.append(f"### Home page:\n{report.home_page}")
        if report.author:
            lines.append(f"### Author:\n{report.author}")
        if report.warnings:
            for warning in report.warnings:
                lines.append(f"### Warning:\n{warning}")

        if report.license_texts:
            for rel_path, text in report.license_texts:
                lines.append("")
                lines.append(f"### License Text (`{rel_path}`)")
                lines.append("")
                lines.append("```text")
                lines.append(text.strip())
                lines.append("```")

        lines.append("")

    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    """
    Parse the command line arguments using `argparse`.
    """
    parser = argparse.ArgumentParser(description="Build a third-party license report.")
    parser.add_argument(
        "--lock-file",
        type=Path,
        default=DEFAULT_LOCK_PATH,
        help="Path to the uv.lock file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Destination file for the generated report",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING)

    if not args.lock_file.exists():
        logging.error(f"lock file not found: {args.lock_file}")
        return 1

    packages = load_packages(args.lock_file)
    if not packages:
        logging.error(f"no packages found in {args.lock_file}")
        return 1

    reports: list[PackageReport] = []
    for name, version in packages.items():
        report = build_report(name, version)
        reports.append(report)
        if args.verbose and report.warnings:
            for warning in report.warnings:
                logging.warning(f"{name}: {warning}")
        if args.verbose and report.infos:
            for info in report.infos:
                logging.info(f"{name}: {info}")

    write_output(reports, args.output)

    # change the log level to INFO so this gets shown no matter what
    logging.getLogger().setLevel(logging.INFO)
    logging.info(f"wrote license report for {len(reports)} packages to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
