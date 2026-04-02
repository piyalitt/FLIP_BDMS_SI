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

"""Generate a unique API key for a trust and output its SHA-256 hash.

Usage:
    uv run python -m flip_api.scripts.generate_trust_key --trust-name Trust_1

The script:
1. Generates a cryptographically secure random key
2. Computes the SHA-256 hex digest (for TRUST_API_KEY_HASHES on the hub)
3. Saves the plaintext key to trust/trust-keys/<trust-name>.key
4. Prints both values to stdout
"""

import argparse
import hashlib
import secrets
from pathlib import Path


def generate_trust_key(trust_name: str, output_dir: Path | None = None) -> tuple[str, str]:
    """Generate a trust API key and its SHA-256 hash.

    Args:
        trust_name (str): The trust name (e.g. "Trust_1").
        output_dir (Path | None): Directory to save the plaintext key file. If None, uses trust/trust-keys/.

    Returns:
        tuple[str, str]: Tuple of (plaintext_key, sha256_hex_hash).
    """
    key = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(key.encode()).hexdigest()

    if output_dir is None:
        output_dir = Path(__file__).resolve().parents[4] / "trust" / "trust-keys"

    output_dir.mkdir(parents=True, exist_ok=True)
    key_file = output_dir / f"{trust_name}.key"
    key_file.write_text(key)

    return key, key_hash


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a unique API key for a trust.")
    parser.add_argument("--trust-name", required=True, help="Trust name (e.g. Trust_1)")
    args = parser.parse_args()

    key, key_hash = generate_trust_key(args.trust_name)

    print(f"Trust:     {args.trust_name}")
    print(f"API Key:   {key}")
    print(f"Key Hash:  {key_hash}")
    print(f"Key saved: trust/trust-keys/{args.trust_name}.key")
    print()
    print(f'Add to TRUST_API_KEY_HASHES: "{args.trust_name}": "{key_hash}"')


if __name__ == "__main__":
    main()
