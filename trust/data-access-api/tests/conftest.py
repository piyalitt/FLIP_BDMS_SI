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

import os

# Set dummy environment variables required by Settings() before any app code
# is imported.  These are only used in tests; real values come from Docker
# Compose environment or .env files in deployed environments.
_TEST_ENV_DEFAULTS = {
    "DATA_ACCESS_POSTGRES_USER": "test_user",
    "DATA_ACCESS_POSTGRES_PASSWORD": "test_password",
    "OMOP_POSTGRES_DB": "test_omop_db",
    "AES_KEY_BASE64": "QgZ+TBA0lUxcuCiRPLneFe/JjMaUEUJWHACHHGz2gGA=",  # 32-byte key, base64
}

for key, value in _TEST_ENV_DEFAULTS.items():
    # Treat unset *and* unreplaced `<placeholder>` values from .env.development.example
    # as missing — otherwise the placeholder leaks through and base64-decoding the
    # AES key fails with "Incorrect padding" mid-test.
    current = os.environ.get(key, "")
    if not current or (current.startswith("<") and current.endswith(">")):
        os.environ[key] = value
