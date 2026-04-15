# Copyright (c) 2026 Guy's and St Thomas' NHS Foundation Trust & King's College London
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""Fail when a pyproject dependency list contains duplicate package entries."""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _normalize_name(requirement: str) -> str:
    """Extract and normalize the package name from a requirement string."""
    match = _NAME_RE.match(requirement)
    if not match:
        return ""
    return re.sub(r"[-_.]+", "-", match.group(1)).lower()


def _find_duplicates(requirements: Iterable[str]) -> dict[str, list[str]]:
    """Return duplicate requirements by normalized package name."""
    seen: dict[str, list[str]] = defaultdict(list)
    for requirement in requirements:
        if not isinstance(requirement, str):
            continue
        name = _normalize_name(requirement)
        if not name:
            continue
        seen[name].append(requirement)

    return {name: entries for name, entries in seen.items() if len(entries) > 1}


def _check_file(path: Path) -> list[str]:
    """Return human-readable duplicate dependency errors for one pyproject file."""
    with path.open("rb") as handle:
        data = tomllib.load(handle)

    errors: list[str] = []

    project_deps = data.get("project", {}).get("dependencies", [])
    if isinstance(project_deps, list):
        duplicates = _find_duplicates(project_deps)
        for package_name, entries in sorted(duplicates.items()):
            errors.append(f"{path}: [project.dependencies] has duplicate '{package_name}' entries: {entries}")

    dependency_groups = data.get("dependency-groups", {})
    if isinstance(dependency_groups, dict):
        for group_name, group_deps in sorted(dependency_groups.items()):
            if not isinstance(group_deps, list):
                continue
            duplicates = _find_duplicates(group_deps)
            for package_name, entries in sorted(duplicates.items()):
                errors.append(
                    f"{path}: [dependency-groups.{group_name}] has duplicate '{package_name}' entries: {entries}"
                )

    optional_deps = data.get("project", {}).get("optional-dependencies", {})
    if isinstance(optional_deps, dict):
        for extra_name, extra_deps in sorted(optional_deps.items()):
            if not isinstance(extra_deps, list):
                continue
            duplicates = _find_duplicates(extra_deps)
            for package_name, entries in sorted(duplicates.items()):
                errors.append(
                    f"{path}: [project.optional-dependencies.{extra_name}] has duplicate "
                    f"'{package_name}' entries: {entries}"
                )

    return errors


def main() -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Check pyproject dependency arrays for duplicate package entries.")
    parser.add_argument(
        "--file",
        dest="files",
        action="append",
        required=True,
        help="Path to a pyproject.toml file. Pass --file multiple times for multiple files.",
    )
    args = parser.parse_args()

    all_errors: list[str] = []
    for file_path in args.files:
        path = Path(file_path)
        if not path.exists():
            all_errors.append(f"{path}: file not found")
            continue
        all_errors.extend(_check_file(path))

    if all_errors:
        print("Duplicate dependency entries detected:", file=sys.stderr)
        for error in all_errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("No duplicate dependency entries found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
