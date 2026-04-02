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

from flip_api.scripts.generate_trust_api_keys import _is_placeholder, main

ENV_TEMPLATE = """\
SOME_VAR=foo
PRIVATE_API_KEY_HEADER=Authorization
PRIVATE_API_KEY_TRUST_1=<placeholder>
PRIVATE_API_KEY_TRUST_2=<placeholder>
TRUST_API_KEY_HASHES={{"Trust_1": "<hash1>", "Trust_2": "<hash2>"}}
OTHER_VAR=bar
"""


class TestIsPlaceholder:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("", True),
            ("<placeholder>", True),
            ("<generate-with-make-generate-trust-key>", True),
            ('{"Trust_1": "<hash>"}', True),
            ("bLYIayFxl2m_lJ2oGU1ZWhQGSNz7qp41MH6_Ggk3f-o", False),
            ("aedgZ7S6n8kqPjpSQOqffhYLXkx2_jGQq5cBtrZFAtU", False),
        ],
    )
    def test_is_placeholder(self, value, expected):
        assert _is_placeholder(value) == expected


class TestGenerateTrustApiKeys:
    def test_updates_env_file_in_place(self, tmp_path):
        """main() should replace placeholders with real keys and hashes."""
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

        # Keys replaced (no longer placeholders)
        trust_1_line = [line for line in lines if line.startswith("PRIVATE_API_KEY_TRUST_1=")][0]
        trust_2_line = [line for line in lines if line.startswith("PRIVATE_API_KEY_TRUST_2=")][0]
        assert trust_1_line != "PRIVATE_API_KEY_TRUST_1=<placeholder>"
        assert trust_2_line != "PRIVATE_API_KEY_TRUST_2=<placeholder>"

        # Hashes line is valid JSON with both trusts
        hashes_line = [line for line in lines if line.startswith("TRUST_API_KEY_HASHES=")][0]
        hashes_json = hashes_line.split("=", 1)[1]
        hashes = json.loads(hashes_json)
        assert "TRUST_1" in hashes
        assert "TRUST_2" in hashes
        assert len(hashes["TRUST_1"]) == 64
        assert len(hashes["TRUST_2"]) == 64

        # Key files written
        key_dir = tmp_path / "trust" / "trust-keys"
        assert (key_dir / "TRUST_1.key").exists()
        assert (key_dir / "TRUST_2.key").exists()

    def test_exits_when_env_file_missing(self, tmp_path):
        """main() should exit with error when env file does not exist."""
        env_file = tmp_path / ".env.nonexistent"

        with (
            patch("sys.argv", ["generate_trust_api_keys", "--env-file", str(env_file)]),
            pytest.raises(SystemExit, match="1"),
        ):
            main()

    def test_exits_when_no_trust_keys_found(self, tmp_path):
        """main() should exit with error when no PRIVATE_API_KEY_TRUST_<N> entries exist."""
        env_file = tmp_path / ".env.test"
        env_file.write_text("SOME_VAR=foo\nOTHER_VAR=bar\n")

        with (
            patch("sys.argv", ["generate_trust_api_keys", "--env-file", str(env_file)]),
            pytest.raises(SystemExit, match="1"),
        ):
            main()

    def test_skips_already_generated_keys(self, tmp_path):
        """main() should preserve existing real keys and not regenerate them."""
        existing_key = "bLYIayFxl2m_lJ2oGU1ZWhQGSNz7qp41MH6_Ggk3f-o"
        env_content = (
            "SOME_VAR=foo\n"
            f"PRIVATE_API_KEY_TRUST_1={existing_key}\n"
            "PRIVATE_API_KEY_TRUST_2=<placeholder>\n"
            'TRUST_API_KEY_HASHES={"Trust_1": "<hash1>", "Trust_2": "<hash2>"}\n'
        )
        env_file = tmp_path / ".env.test"
        env_file.write_text(env_content)

        with (
            patch("flip_api.scripts.generate_trust_api_keys.REPO_ROOT", tmp_path),
            patch("sys.argv", ["generate_trust_api_keys", "--env-file", str(env_file)]),
        ):
            main()

        content = env_file.read_text()
        lines = content.splitlines()

        # Trust 1 key preserved
        trust_1_line = [line for line in lines if line.startswith("PRIVATE_API_KEY_TRUST_1=")][0]
        assert trust_1_line == f"PRIVATE_API_KEY_TRUST_1={existing_key}"

        # Trust 2 key generated (no longer placeholder)
        trust_2_line = [line for line in lines if line.startswith("PRIVATE_API_KEY_TRUST_2=")][0]
        assert trust_2_line != "PRIVATE_API_KEY_TRUST_2=<placeholder>"
        trust_2_key = trust_2_line.split("=", 1)[1]
        assert "<" not in trust_2_key

        # Hashes updated for both trusts
        hashes_line = [line for line in lines if line.startswith("TRUST_API_KEY_HASHES=")][0]
        hashes = json.loads(hashes_line.split("=", 1)[1])
        assert len(hashes) == 2
        # Trust 1 hash matches existing key
        assert hashes["TRUST_1"] == hashlib.sha256(existing_key.encode()).hexdigest()

    def test_force_regenerates_all_keys(self, tmp_path):
        """--force should regenerate keys even when they already have real values."""
        existing_key = "bLYIayFxl2m_lJ2oGU1ZWhQGSNz7qp41MH6_Ggk3f-o"
        env_content = (
            f"PRIVATE_API_KEY_TRUST_1={existing_key}\n"
            'TRUST_API_KEY_HASHES={"Trust_1": "<hash>"}\n'
        )
        env_file = tmp_path / ".env.test"
        env_file.write_text(env_content)

        with (
            patch("flip_api.scripts.generate_trust_api_keys.REPO_ROOT", tmp_path),
            patch("sys.argv", ["generate_trust_api_keys", "--env-file", str(env_file), "--force"]),
        ):
            main()

        content = env_file.read_text()
        lines = content.splitlines()

        trust_1_line = [line for line in lines if line.startswith("PRIVATE_API_KEY_TRUST_1=")][0]
        new_key = trust_1_line.split("=", 1)[1]
        assert new_key != existing_key
        assert "<" not in new_key
