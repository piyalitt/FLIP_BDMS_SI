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

"""Generate per-trust API keys and write hashes into an environment file.

Trust names are read from the ``TRUST_NAMES`` env var (a JSON list).  Plaintext
keys are stored in ``trust/trust-keys/<name>.key`` files, and only the hashes
are written back into the environment file as ``TRUST_API_KEY_HASHES``.

Usage:
    make generate-trust-api-keys
    make generate-trust-api-keys ENV_FILE=.env.stag
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from flip_api.scripts.generate_trust_key import generate_trust_key

REPO_ROOT = Path(__file__).resolve().parents[4]


def _parse_trust_names(lines: list[str]) -> list[str]:
    """Extract trust names from the TRUST_NAMES env var line.

    Args:
        lines (list[str]): Lines of the environment file.

    Returns:
        list[str]: List of trust names, e.g. ``["Trust_1", "Trust_2"]``.
    """
    for line in lines:
        if line.startswith("TRUST_NAMES="):
            return json.loads(line.split("=", 1)[1])
    return []


def main() -> None:
    """Generate per-trust API keys and write hashes into the specified environment file.

    Reads trust names from ``TRUST_NAMES``, generates a cryptographically secure
    key for each trust that doesn't already have a ``.key`` file (or all if
    ``--force``), and updates ``TRUST_API_KEY_HASHES`` in the env file.

    Raises:
        SystemExit: If the env file is missing or contains no ``TRUST_NAMES`` entry.
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
        help="Regenerate all keys even if they already have .key files.",
    )
    args = parser.parse_args()
    env_file: Path = args.env_file

    if not env_file.exists():
        print(f"Error: {env_file} not found.")
        sys.exit(1)

    lines = env_file.read_text().splitlines()

    trust_names = _parse_trust_names(lines)
    if not trust_names:
        print(f"Error: no TRUST_NAMES entry found in {env_file.name}.")
        sys.exit(1)

    # Generate keys — existing .key files are preserved unless --force
    key_dir = REPO_ROOT / "trust" / "trust-keys"
    trust_keys: dict[str, tuple[str, str]] = {}
    actions: dict[str, str] = {}
    for trust_name in trust_names:
        key_file = key_dir / f"{trust_name}.key"
        if not args.force and key_file.exists() and key_file.read_text().strip():
            existing_key = key_file.read_text().strip()
            key_hash = hashlib.sha256(existing_key.encode()).hexdigest()
            trust_keys[trust_name] = (existing_key, key_hash)
            actions[trust_name] = "skipped"
        else:
            key, key_hash = generate_trust_key(trust_name, output_dir=key_dir)
            trust_keys[trust_name] = (key, key_hash)
            actions[trust_name] = "generated"

    # Build TRUST_API_KEY_HASHES value
    hashes_dict = {name: trust_keys[name][1] for name in trust_names}
    hashes_json = json.dumps(hashes_dict)

    # Rewrite lines
    new_lines: list[str] = []
    for line in lines:
        if line.startswith("TRUST_API_KEY_HASHES="):
            new_lines.append(f"TRUST_API_KEY_HASHES={hashes_json}")
        else:
            new_lines.append(line)

    env_file.write_text("\n".join(new_lines) + "\n")

    generated = sum(1 for a in actions.values() if a == "generated")
    skipped = sum(1 for a in actions.values() if a == "skipped")
    print(f"Updated {env_file.name}: {generated} trust keys generated, {skipped} skipped (already set).")
    for name, action in actions.items():
        print(f"  {name}: {action}")
    if generated:
        print(f"  TRUST_API_KEY_HASHES updated with {len(trust_names)} entries")


if __name__ == "__main__":
    main()
