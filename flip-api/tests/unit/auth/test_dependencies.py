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

from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from flip_api.auth.dependencies import verify_token

TEST_REGION = "eu-west-2"
TEST_USER_POOL_ID = "eu-west-2_TESTPOOL"
TEST_APP_CLIENT_ID = "test-app-client-id"
EXPECTED_ISSUER = f"https://cognito-idp.{TEST_REGION}.amazonaws.com/{TEST_USER_POOL_ID}"
EXPECTED_JWKS_URL = f"{EXPECTED_ISSUER}/.well-known/jwks.json"

PATCH_GET_SETTINGS = "flip_api.auth.dependencies.get_settings"
PATCH_PYJWK_CLIENT = "flip_api.auth.dependencies.PyJWKClient"
PATCH_JWT_DECODE = "flip_api.auth.dependencies.jwt.decode"


@pytest.fixture
def mock_settings():
    with patch(PATCH_GET_SETTINGS) as m:
        settings = MagicMock()
        settings.AWS_REGION = TEST_REGION
        settings.AWS_COGNITO_USER_POOL_ID = TEST_USER_POOL_ID
        settings.AWS_COGNITO_APP_CLIENT_ID = TEST_APP_CLIENT_ID
        m.return_value = settings
        yield m


@pytest.fixture
def mock_jwks():
    with patch(PATCH_PYJWK_CLIENT) as jwks_client_cls:
        signing_key = MagicMock()
        signing_key.key = "fake-public-key"
        jwks_client = MagicMock()
        jwks_client.get_signing_key_from_jwt.return_value = signing_key
        jwks_client_cls.return_value = jwks_client
        yield jwks_client_cls


def _credentials(token: str = "fake.jwt.token") -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _id_token_payload(sub: str | None = None, aud: str = TEST_APP_CLIENT_ID) -> dict:
    return {
        "sub": sub or str(uuid4()),
        "aud": aud,
        "iss": EXPECTED_ISSUER,
        "token_use": "id",
        "exp": 9999999999,
    }


def _access_token_payload(sub: str | None = None, client_id: str = TEST_APP_CLIENT_ID) -> dict:
    return {
        "sub": sub or str(uuid4()),
        "client_id": client_id,
        "iss": EXPECTED_ISSUER,
        "token_use": "access",
        "exp": 9999999999,
    }


class TestVerifyTokenSuccess:
    def test_valid_id_token_returns_user_uuid(self, mock_settings, mock_jwks):
        sub = str(uuid4())
        with patch(PATCH_JWT_DECODE, return_value=_id_token_payload(sub=sub)):
            user_id = verify_token(_credentials())
        assert user_id == UUID(sub)

    def test_valid_access_token_returns_user_uuid(self, mock_settings, mock_jwks):
        sub = str(uuid4())
        with patch(PATCH_JWT_DECODE, return_value=_access_token_payload(sub=sub)):
            user_id = verify_token(_credentials())
        assert user_id == UUID(sub)

    def test_jwt_decode_called_with_issuer_and_algorithm(self, mock_settings, mock_jwks):
        with patch(PATCH_JWT_DECODE, return_value=_id_token_payload()) as decode:
            verify_token(_credentials())
        kwargs = decode.call_args.kwargs
        assert kwargs["algorithms"] == ["RS256"]
        assert kwargs["issuer"] == EXPECTED_ISSUER
        assert kwargs["options"]["verify_aud"] is False
        assert set(kwargs["options"]["require"]) >= {"exp", "iss", "sub", "token_use"}

    def test_jwks_url_uses_configured_pool(self, mock_settings, mock_jwks):
        with patch(PATCH_JWT_DECODE, return_value=_id_token_payload()):
            verify_token(_credentials())
        mock_jwks.assert_called_once_with(EXPECTED_JWKS_URL)


class TestVerifyTokenAudienceValidation:
    def test_id_token_with_wrong_aud_rejected(self, mock_settings, mock_jwks):
        payload = _id_token_payload(aud="some-other-app-client")
        with patch(PATCH_JWT_DECODE, return_value=payload):
            with pytest.raises(HTTPException) as exc_info:
                verify_token(_credentials())
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == "Could not validate credentials"

    def test_id_token_missing_aud_rejected(self, mock_settings, mock_jwks):
        payload = _id_token_payload()
        del payload["aud"]
        with patch(PATCH_JWT_DECODE, return_value=payload):
            with pytest.raises(HTTPException) as exc_info:
                verify_token(_credentials())
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    def test_access_token_with_wrong_client_id_rejected(self, mock_settings, mock_jwks):
        payload = _access_token_payload(client_id="some-other-app-client")
        with patch(PATCH_JWT_DECODE, return_value=payload):
            with pytest.raises(HTTPException) as exc_info:
                verify_token(_credentials())
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    def test_access_token_missing_client_id_rejected(self, mock_settings, mock_jwks):
        payload = _access_token_payload()
        del payload["client_id"]
        with patch(PATCH_JWT_DECODE, return_value=payload):
            with pytest.raises(HTTPException) as exc_info:
                verify_token(_credentials())
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    def test_unknown_token_use_rejected(self, mock_settings, mock_jwks):
        payload = _id_token_payload()
        payload["token_use"] = "refresh"
        with patch(PATCH_JWT_DECODE, return_value=payload):
            with pytest.raises(HTTPException) as exc_info:
                verify_token(_credentials())
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


class TestVerifyTokenJwtErrors:
    def test_expired_token_returns_specific_message(self, mock_settings, mock_jwks):
        with patch(PATCH_JWT_DECODE, side_effect=jwt.ExpiredSignatureError):
            with pytest.raises(HTTPException) as exc_info:
                verify_token(_credentials())
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == "Token has expired"

    def test_invalid_issuer_returns_401(self, mock_settings, mock_jwks):
        with patch(PATCH_JWT_DECODE, side_effect=jwt.InvalidIssuerError("bad issuer")):
            with pytest.raises(HTTPException) as exc_info:
                verify_token(_credentials())
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == "Could not validate credentials"

    def test_invalid_signature_returns_401(self, mock_settings, mock_jwks):
        with patch(PATCH_JWT_DECODE, side_effect=jwt.InvalidSignatureError):
            with pytest.raises(HTTPException) as exc_info:
                verify_token(_credentials())
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    def test_missing_required_claim_returns_401(self, mock_settings, mock_jwks):
        with patch(PATCH_JWT_DECODE, side_effect=jwt.MissingRequiredClaimError("exp")):
            with pytest.raises(HTTPException) as exc_info:
                verify_token(_credentials())
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


class TestVerifyTokenSubject:
    def test_non_uuid_sub_rejected(self, mock_settings, mock_jwks):
        payload = _id_token_payload(sub="not-a-uuid")
        with patch(PATCH_JWT_DECODE, return_value=payload):
            with pytest.raises(HTTPException) as exc_info:
                verify_token(_credentials())
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == "Invalid user identifier format"


class TestVerifyTokenUnexpectedErrors:
    def test_jwks_fetch_failure_returns_500(self, mock_settings):
        with patch(PATCH_PYJWK_CLIENT, side_effect=RuntimeError("network down")):
            with pytest.raises(HTTPException) as exc_info:
                verify_token(_credentials())
        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
