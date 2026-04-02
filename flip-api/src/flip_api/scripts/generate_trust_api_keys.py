# Copyright (c) Guy's and St Thomas' NHS Foundation Trust & King's College London
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

"""Generate per-trust API keys for all trusts and write them into an environment file.

Usage:
    make generate-trust-api-keys
    make generate-trust-api-keys ENV_FILE=.env.stag
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from flip_api.scripts.generate_trust_key import generate_trust_key

REPO_ROOT = Path(__file__).resolve().parents[4]
TRUST_KEY_PATTERN = re.compile(r"^PRIVATE_API_KEY_(TRUST_\d+)=(.*)$")


def _is_placeholder(value: str) -> bool:
    """Return True if the value is empty or looks like a template placeholder.

    Args:
        value (str): The env var value to inspect.

    Returns:
        bool: True if the value is empty or contains a '<' character.
    """
    return not value or "<" in value


def main() -> None:
    """Generate per-trust API keys and write them into the specified environment file.

    Reads the environment file to discover PRIVATE_API_KEY_TRUST_<N> entries,
    generates a cryptographically secure key for each placeholder (or all if --force),
    and updates the file in-place with the new keys and TRUST_API_KEY_HASHES.

    Raises:
        SystemExit: If the env file is missing or contains no trust key entries.
    """
    parser = argparse.ArgumentParser(description="Generate per-trust API keys and update an environment file.")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=REPO_ROOT / ".env.development",
        help="Path to the environment file to update (default: .env.development)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Regenerate all keys even if they already have real values.",
    )
    args = parser.parse_args()
    env_file: Path = args.env_file

    if not env_file.exists():
        print(f"Error: {env_file} not found.")
        sys.exit(1)

    lines = env_file.read_text().splitlines()

    # Discover trusts from PRIVATE_API_KEY_TRUST_<N> lines
    trust_entries: dict[str, str] = {}
    for line in lines:
        match = TRUST_KEY_PATTERN.match(line)
        if match:
            trust_entries[match.group(1)] = match.group(2)

    if not trust_entries:
        print(f"Error: no PRIVATE_API_KEY_TRUST_<N> entries found in {env_file.name}.")
        sys.exit(1)

    # Generate keys only for placeholders (or all if --force)
    trust_keys: dict[str, tuple[str, str]] = {}
    key_dir = REPO_ROOT / "trust" / "trust-keys"
    generated = 0
    skipped = 0
    for trust_name, existing_value in trust_entries.items():
        if not args.force and not _is_placeholder(existing_value):
            key_hash = hashlib.sha256(existing_value.encode()).hexdigest()
            trust_keys[trust_name] = (existing_value, key_hash)
            skipped += 1
        else:
            key, key_hash = generate_trust_key(trust_name, output_dir=key_dir)
            trust_keys[trust_name] = (key, key_hash)
            generated += 1

    # Build TRUST_API_KEY_HASHES value
    hashes_dict = {name: trust_keys[name][1] for name in trust_entries}
    hashes_json = json.dumps(hashes_dict)

    # Rewrite lines
    new_lines: list[str] = []
    for line in lines:
        match = TRUST_KEY_PATTERN.match(line)
        if match:
            trust_name = match.group(1)
            new_lines.append(f"PRIVATE_API_KEY_{trust_name}={trust_keys[trust_name][0]}")
        elif line.startswith("TRUST_API_KEY_HASHES="):
            new_lines.append(f"TRUST_API_KEY_HASHES={hashes_json}")
        else:
            new_lines.append(line)

    env_file.write_text("\n".join(new_lines) + "\n")

    print(f"Updated {env_file.name}: {generated} generated, {skipped} skipped (already set).")
    for name in trust_entries:
        action = "generated" if args.force or _is_placeholder(trust_entries[name]) else "skipped"
        print(f"  {name}: {action}")
    if generated:
        print(f"  TRUST_API_KEY_HASHES updated with {len(trust_entries)} entries")


if __name__ == "__main__":
    main()
