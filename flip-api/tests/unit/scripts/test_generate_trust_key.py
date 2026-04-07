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

from flip_api.scripts.generate_trust_key import generate_trust_key


class TestGenerateTrustKey:
    def test_returns_key_and_hash(self, tmp_path):
        """generate_trust_key should return a non-empty key and its SHA-256 hash."""
        key, key_hash = generate_trust_key("Trust_Test", output_dir=tmp_path)

        assert isinstance(key, str)
        assert len(key) > 0
        assert isinstance(key_hash, str)
        assert len(key_hash) == 64  # SHA-256 hex digest length

    def test_hash_matches_sha256_of_key(self, tmp_path):
        """The returned hash must equal hashlib.sha256(key.encode()).hexdigest()."""
        key, key_hash = generate_trust_key("Trust_Hash", output_dir=tmp_path)

        expected_hash = hashlib.sha256(key.encode()).hexdigest()
        assert key_hash == expected_hash

    def test_key_file_written_to_output_directory(self, tmp_path):
        """The plaintext key should be written to <output_dir>/<trust_name>.key."""
        trust_name = "Trust_FileWrite"
        key, _ = generate_trust_key(trust_name, output_dir=tmp_path)

        key_file = tmp_path / f"{trust_name}.key"
        assert key_file.exists()
        assert key_file.read_text() == key

    def test_output_directory_created_if_missing(self, tmp_path):
        """generate_trust_key should create the output directory when it does not exist."""
        nested_dir = tmp_path / "nested" / "keys"
        assert not nested_dir.exists()

        key, _ = generate_trust_key("Trust_Nested", output_dir=nested_dir)

        assert nested_dir.exists()
        assert (nested_dir / "Trust_Nested.key").read_text() == key


class TestGenerateTrustKeyMain:
    def test_main_prints_key_info(self, tmp_path, capsys):
        """main() should print the trust name, key, hash, and key file path."""
        from unittest.mock import patch

        with (
            patch("sys.argv", ["generate_trust_key", "--trust-name", "Trust_CLI"]),
            patch("flip_api.scripts.generate_trust_key.Path.resolve", return_value=tmp_path / "fake"),
            patch(
                "flip_api.scripts.generate_trust_key.generate_trust_key",
                return_value=("test-key-abc", "test-hash-def"),
            ) as mock_gen,
        ):
            from flip_api.scripts.generate_trust_key import main

            main()

        mock_gen.assert_called_once_with("Trust_CLI")
        captured = capsys.readouterr()
        assert "Trust_CLI" in captured.out
        assert "test-key-abc" in captured.out
        assert "test-hash-def" in captured.out
