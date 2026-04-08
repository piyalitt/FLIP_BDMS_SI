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

import hashlib
import json
from unittest.mock import patch

import pytest

from flip_api.scripts.generate_trust_api_keys import main

ENV_TEMPLATE = """\
SOME_VAR=foo
PRIVATE_API_KEY_HEADER=Authorization
TRUST_NAMES=["Trust_1", "Trust_2"]
TRUST_API_KEY_HASHES={{"Trust_1": "<hash1>", "Trust_2": "<hash2>"}}
OTHER_VAR=bar
"""


class TestGenerateTrustApiKeys:
    def test_generates_keys_and_updates_hashes(self, tmp_path):
        """main() should generate .key files and update TRUST_API_KEY_HASHES."""
        env_file = tmp_path / ".env.test"
        env_file.write_text(ENV_TEMPLATE)

        with (
            patch("flip_api.scripts.generate_trust_api_keys.REPO_ROOT", tmp_path),
            patch("sys.argv", ["generate_trust_api_keys", "--env-file", str(env_file)]),
        ):
            main()

        content = env_file.read_text()
        lines = content.splitlines()

        # Unchanged lines preserved
        assert "SOME_VAR=foo" in lines
        assert "OTHER_VAR=bar" in lines
        assert "PRIVATE_API_KEY_HEADER=Authorization" in lines

        # Hashes line is valid JSON with canonical trust names
        hashes_line = [line for line in lines if line.startswith("TRUST_API_KEY_HASHES=")][0]
        hashes_json = hashes_line.split("=", 1)[1]
        hashes = json.loads(hashes_json)
        assert "Trust_1" in hashes
        assert "Trust_2" in hashes
        assert len(hashes["Trust_1"]) == 64
        assert len(hashes["Trust_2"]) == 64

        # Key files written with canonical names
        key_dir = tmp_path / "trust" / "trust-keys"
        assert (key_dir / "Trust_1.key").exists()
        assert (key_dir / "Trust_2.key").exists()

        # Key file contents match hashes
        for name in ("Trust_1", "Trust_2"):
            key = (key_dir / f"{name}.key").read_text()
            assert hashes[name] == hashlib.sha256(key.encode()).hexdigest()

    def test_exits_when_env_file_missing(self, tmp_path):
        """main() should exit with error when env file does not exist."""
        env_file = tmp_path / ".env.nonexistent"

        with (
            patch("sys.argv", ["generate_trust_api_keys", "--env-file", str(env_file)]),
            pytest.raises(SystemExit, match="1"),
        ):
            main()

    def test_exits_when_no_trust_names_found(self, tmp_path):
        """main() should exit with error when no TRUST_NAMES entry exists."""
        env_file = tmp_path / ".env.test"
        env_file.write_text("SOME_VAR=foo\nOTHER_VAR=bar\n")

        with (
            patch("sys.argv", ["generate_trust_api_keys", "--env-file", str(env_file)]),
            pytest.raises(SystemExit, match="1"),
        ):
            main()

    def test_skips_existing_key_files(self, tmp_path):
        """main() should preserve existing .key files and not regenerate them."""
        existing_key = "bLYIayFxl2m_lJ2oGU1ZWhQGSNz7qp41MH6_Ggk3f-o"
        key_dir = tmp_path / "trust" / "trust-keys"
        key_dir.mkdir(parents=True)
        (key_dir / "Trust_1.key").write_text(existing_key)

        env_file = tmp_path / ".env.test"
        env_file.write_text(ENV_TEMPLATE)

        with (
            patch("flip_api.scripts.generate_trust_api_keys.REPO_ROOT", tmp_path),
            patch("sys.argv", ["generate_trust_api_keys", "--env-file", str(env_file)]),
        ):
            main()

        # Trust_1 key file preserved
        assert (key_dir / "Trust_1.key").read_text() == existing_key

        # Trust_2 key file generated
        trust_2_key = (key_dir / "Trust_2.key").read_text()
        assert trust_2_key
        assert trust_2_key != existing_key

        # Hashes updated for both trusts
        content = env_file.read_text()
        hashes_line = [line for line in content.splitlines() if line.startswith("TRUST_API_KEY_HASHES=")][0]
        hashes = json.loads(hashes_line.split("=", 1)[1])
        assert len(hashes) == 2
        assert hashes["Trust_1"] == hashlib.sha256(existing_key.encode()).hexdigest()

    def test_force_regenerates_all_keys(self, tmp_path):
        """--force should regenerate keys even when .key files already exist."""
        existing_key = "bLYIayFxl2m_lJ2oGU1ZWhQGSNz7qp41MH6_Ggk3f-o"
        key_dir = tmp_path / "trust" / "trust-keys"
        key_dir.mkdir(parents=True)
        (key_dir / "Trust_1.key").write_text(existing_key)

        env_file = tmp_path / ".env.test"
        env_file.write_text(ENV_TEMPLATE)

        with (
            patch("flip_api.scripts.generate_trust_api_keys.REPO_ROOT", tmp_path),
            patch("sys.argv", ["generate_trust_api_keys", "--env-file", str(env_file), "--force"]),
        ):
            main()

        new_key = (key_dir / "Trust_1.key").read_text()
        assert new_key != existing_key
