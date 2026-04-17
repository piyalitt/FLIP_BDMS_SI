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

import uuid
from unittest.mock import patch

import pytest
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from flip_api.auth.dependencies import verify_token, verify_token_no_mfa


@pytest.fixture
def user_sub():
    return str(uuid.uuid4())


@pytest.fixture
def credentials():
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials="dummy.jwt.token")


def _payload(user_sub: str, username: str = "user@example.com") -> dict:
    return {"sub": user_sub, "username": username, "token_use": "access"}


def test_verify_token_allows_mfa_enrolled_caller(credentials, user_sub):
    """Happy path: JWT is valid and MFA is active."""
    with (
        patch("flip_api.auth.dependencies._decode_verified_claims") as mock_decode,
        patch("flip_api.auth.dependencies.is_mfa_enabled") as mock_is_enabled,
    ):
        mock_decode.return_value = _payload(user_sub)
        mock_is_enabled.return_value = True

        result = verify_token(credentials)

        assert str(result) == user_sub
        mock_is_enabled.assert_called_once()


def test_verify_token_rejects_caller_without_mfa(credentials, user_sub):
    """The MFA gate: a valid JWT without active TOTP yields 403."""
    with (
        patch("flip_api.auth.dependencies._decode_verified_claims") as mock_decode,
        patch("flip_api.auth.dependencies.is_mfa_enabled") as mock_is_enabled,
    ):
        mock_decode.return_value = _payload(user_sub)
        mock_is_enabled.return_value = False

        with pytest.raises(HTTPException) as exc_info:
            verify_token(credentials)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "MFA enrolment required" in exc_info.value.detail


def test_verify_token_rejects_token_missing_username(credentials, user_sub):
    """The MFA gate needs the Cognito Username claim; without it we 401 early."""
    with (
        patch("flip_api.auth.dependencies._decode_verified_claims") as mock_decode,
        patch("flip_api.auth.dependencies.is_mfa_enabled") as mock_is_enabled,
    ):
        mock_decode.return_value = {"sub": user_sub, "token_use": "access"}

        with pytest.raises(HTTPException) as exc_info:
            verify_token(credentials)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        mock_is_enabled.assert_not_called()


def test_verify_token_accepts_id_token_username_claim(credentials, user_sub):
    """ID tokens spell the Username claim 'cognito:username'; accept either."""
    with (
        patch("flip_api.auth.dependencies._decode_verified_claims") as mock_decode,
        patch("flip_api.auth.dependencies.is_mfa_enabled") as mock_is_enabled,
    ):
        mock_decode.return_value = {
            "sub": user_sub,
            "cognito:username": "user@example.com",
            "token_use": "id",
        }
        mock_is_enabled.return_value = True

        result = verify_token(credentials)

        assert str(result) == user_sub
        mock_is_enabled.assert_called_once()


def test_verify_token_no_mfa_skips_gate(credentials, user_sub):
    """The bootstrap variant never touches the MFA helper — it's for pre-enrolment callers."""
    with (
        patch("flip_api.auth.dependencies._decode_verified_claims") as mock_decode,
        patch("flip_api.auth.dependencies.is_mfa_enabled") as mock_is_enabled,
    ):
        mock_decode.return_value = _payload(user_sub)

        result = verify_token_no_mfa(credentials)

        assert str(result) == user_sub
        mock_is_enabled.assert_not_called()
