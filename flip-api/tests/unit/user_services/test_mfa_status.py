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

from flip_api.user_services.mfa_status import get_own_mfa_status


@pytest.fixture
def token_id():
    return uuid.uuid4()


def test_returns_enabled_true_when_totp_active(mock_request, token_id):
    """Caller with SOFTWARE_TOKEN_MFA in their settings list gets enabled=True."""
    user_pool_id = "test-user-pool-id"
    username = "user@example.com"

    with (
        patch("flip_api.user_services.mfa_status.get_user_pool_id") as mock_get_pool,
        patch("flip_api.user_services.mfa_status.get_username") as mock_get_username,
        patch("flip_api.user_services.mfa_status.is_mfa_enabled") as mock_is_enabled,
    ):
        mock_get_pool.return_value = user_pool_id
        mock_get_username.return_value = username
        mock_is_enabled.return_value = True

        result = get_own_mfa_status(mock_request, token_id)

        assert result == {"enabled": True}
        mock_get_username.assert_called_once_with(str(token_id), user_pool_id)
        mock_is_enabled.assert_called_once_with(username, user_pool_id)


def test_returns_enabled_false_when_totp_not_active(mock_request, token_id):
    """Post-reset or first-invite user sees enabled=False, which is the cue to enrol."""
    user_pool_id = "test-user-pool-id"
    username = "user@example.com"

    with (
        patch("flip_api.user_services.mfa_status.get_user_pool_id") as mock_get_pool,
        patch("flip_api.user_services.mfa_status.get_username") as mock_get_username,
        patch("flip_api.user_services.mfa_status.is_mfa_enabled") as mock_is_enabled,
    ):
        mock_get_pool.return_value = user_pool_id
        mock_get_username.return_value = username
        mock_is_enabled.return_value = False

        result = get_own_mfa_status(mock_request, token_id)

        assert result == {"enabled": False}


def test_raises_404_when_cognito_user_missing(mock_request, token_id):
    """A valid JWT whose sub has no matching Cognito user bubbles get_username's 404."""
    user_pool_id = "test-user-pool-id"

    with (
        patch("flip_api.user_services.mfa_status.get_user_pool_id") as mock_get_pool,
        patch("flip_api.user_services.mfa_status.get_username") as mock_get_username,
        patch("flip_api.user_services.mfa_status.is_mfa_enabled") as mock_is_enabled,
    ):
        mock_get_pool.return_value = user_pool_id
        mock_get_username.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not registered"
        )

        with pytest.raises(HTTPException) as exc_info:
            get_own_mfa_status(mock_request, token_id)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        mock_is_enabled.assert_not_called()
