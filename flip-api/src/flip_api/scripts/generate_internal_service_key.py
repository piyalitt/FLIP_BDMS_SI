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

"""Generate the internal service key used by fl-server to authenticate with flip-api.

The plaintext key is saved to ``deploy/keys/internal_service.key`` and the
SHA-256 hash is written into ``INTERNAL_SERVICE_KEY_HASH`` in the env file.
Existing keys are preserved unless ``--force`` is used.

At runtime, fl-server reads the plaintext key from the key file (injected by
the Makefile), while flip-api reads the hash from the environment.

Usage:
    make generate-internal-service-key
    make generate-internal-service-key ENV_FILE=.env.stag
    make generate-internal-service-key FORCE=1
"""

import argparse
import hashlib
import secrets
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]


def main() -> None:
    """Generate the internal service key and update the environment file.

    Raises:
        SystemExit: If the env file is missing.
    """
    parser = argparse.ArgumentParser(description="Generate internal service key and update an environment file.")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=REPO_ROOT / ".env.development",
        help="Path to the environment file to update (default: .env.development)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate the key even if it already exists.",
    )
    args = parser.parse_args()
    env_file: Path = args.env_file

    if not env_file.exists():
        print(f"Error: {env_file} not found.")
        sys.exit(1)

    key_dir = REPO_ROOT / "deploy" / "keys"
    key_dir.mkdir(parents=True, exist_ok=True)
    key_file = key_dir / "internal_service.key"

    if key_file.exists() and not args.force:
        print(f"Key already exists: {key_file} (use --force to regenerate)")
        return

    # Generate key
    key = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(key.encode()).hexdigest()

    # Save plaintext to .key file (Central Hub scope, not trust-keys)
    key_file.write_text(key)

    # Update INTERNAL_SERVICE_KEY_HASH in env file
    lines = env_file.read_text().splitlines()
    new_lines: list[str] = []
    for line in lines:
        if line.startswith("INTERNAL_SERVICE_KEY_HASH="):
            new_lines.append(f"INTERNAL_SERVICE_KEY_HASH={key_hash}")
        else:
            new_lines.append(line)
    env_file.write_text("\n".join(new_lines) + "\n")

    print("Generated internal service key:")
    print(f"  Key saved: {key_file}")
    print(f"  INTERNAL_SERVICE_KEY_HASH updated in {env_file.name}")


if __name__ == "__main__":
    main()
