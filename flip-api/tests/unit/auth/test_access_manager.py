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
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException, status
from sqlmodel import Session

# Module to be tested
from flip_api.auth.access_manager import (
    authenticate_internal_service,
    authenticate_trust,
    can_modify_model,
    can_modify_project,
)

VALID_TEST_KEY = "test_secret_key_12345_valid"
VALID_TEST_KEY_HASH = hashlib.sha256(VALID_TEST_KEY.encode()).hexdigest()
WRONG_TEST_KEY = "wrong_secret_key_67890_invalid"
TRUST_NAME = "Trust_1"

INTERNAL_SERVICE_KEY = "internal_service_key_abc123"
INTERNAL_SERVICE_KEY_HASH = hashlib.sha256(INTERNAL_SERVICE_KEY.encode()).hexdigest()

PATCH_HAS_PERMISSIONS = "flip_api.auth.access_manager.has_permissions"
PATCH_CAN_MODIFY_PROJECT = "flip_api.auth.access_manager.can_modify_project"
PATCH_GET_SETTINGS = "flip_api.auth.access_manager.get_settings"


PATCH_HASH_CACHE = "flip_api.auth.access_manager._trust_api_key_hashes_cache"


@pytest.fixture
def mocked_settings():
    mock = MagicMock()
    mock.TRUST_API_KEY_HASHES = {TRUST_NAME: VALID_TEST_KEY_HASH}
    with patch(PATCH_GET_SETTINGS, return_value=mock), patch(PATCH_HASH_CACHE, None):
        yield mock


@pytest.fixture
def mocked_settings_empty():
    mock = MagicMock()
    mock.TRUST_API_KEY_HASHES = {}
    with patch(PATCH_GET_SETTINGS, return_value=mock), patch(PATCH_HASH_CACHE, None):
        yield mock


class TestAuthenticateTrust:
    def test_valid_api_key_returns_trust_name(self, mocked_settings):
        assert authenticate_trust(api_key=VALID_TEST_KEY) == TRUST_NAME

    def test_invalid_api_key_returns_401(self, mocked_settings):
        with pytest.raises(HTTPException) as exc_info:
            authenticate_trust(api_key=WRONG_TEST_KEY)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == "Invalid API Key."

    def test_missing_api_key_returns_401(self, mocked_settings):
        with pytest.raises(HTTPException) as exc_info:
            authenticate_trust(api_key=None)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == "Not authenticated: API key is missing."

    def test_empty_api_key_returns_401(self, mocked_settings):
        with pytest.raises(HTTPException) as exc_info:
            authenticate_trust(api_key="")
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == "Not authenticated: API key is missing."

    def test_no_trust_keys_configured_returns_401(self, mocked_settings_empty):
        with pytest.raises(HTTPException) as exc_info:
            authenticate_trust(api_key=VALID_TEST_KEY)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    def test_multiple_trusts_returns_correct_name(self):
        second_key = "second_trust_key_xyz"
        second_hash = hashlib.sha256(second_key.encode()).hexdigest()
        mock = MagicMock()
        mock.TRUST_API_KEY_HASHES = {TRUST_NAME: VALID_TEST_KEY_HASH, "Trust_2": second_hash}
        with patch(PATCH_GET_SETTINGS, return_value=mock), patch(PATCH_HASH_CACHE, None):
            assert authenticate_trust(api_key=VALID_TEST_KEY) == TRUST_NAME
            assert authenticate_trust(api_key=second_key) == "Trust_2"


class TestAuthenticateInternalService:
    """Tests for the authenticate_internal_service dependency."""

    def test_valid_key_succeeds(self):
        """Valid internal service key should not raise an exception."""
        mock = MagicMock()
        mock.INTERNAL_SERVICE_KEY_HASH = INTERNAL_SERVICE_KEY_HASH
        with patch(PATCH_GET_SETTINGS, return_value=mock):
            result = authenticate_internal_service(api_key=INTERNAL_SERVICE_KEY)
        assert result is None

    def test_missing_key_returns_401(self):
        """Missing (None) key should raise 401."""
        with pytest.raises(HTTPException) as exc_info:
            authenticate_internal_service(api_key=None)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == "Not authenticated: internal service key is missing."

    def test_empty_key_returns_401(self):
        """Empty string key should raise 401."""
        with pytest.raises(HTTPException) as exc_info:
            authenticate_internal_service(api_key="")
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == "Not authenticated: internal service key is missing."

    def test_invalid_key_returns_401(self):
        """Wrong key should raise 401."""
        mock = MagicMock()
        mock.INTERNAL_SERVICE_KEY_HASH = INTERNAL_SERVICE_KEY_HASH
        with patch(PATCH_GET_SETTINGS, return_value=mock):
            with pytest.raises(HTTPException) as exc_info:
                authenticate_internal_service(api_key=WRONG_TEST_KEY)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == "Invalid internal service key."

    def test_unconfigured_hash_returns_401(self):
        """Empty INTERNAL_SERVICE_KEY_HASH should raise 401."""
        mock = MagicMock()
        mock.INTERNAL_SERVICE_KEY_HASH = ""
        with patch(PATCH_GET_SETTINGS, return_value=mock):
            with pytest.raises(HTTPException) as exc_info:
                authenticate_internal_service(api_key=INTERNAL_SERVICE_KEY)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == "Internal service auth not configured."


class TestCanModifyProject:
    def test_returns_true_when_user_has_manage_projects_permission(self):
        user_id = uuid4()
        project_id = uuid4()
        db = MagicMock(spec=Session)

        with patch(PATCH_HAS_PERMISSIONS, return_value=True):
            result = can_modify_project(user_id, project_id, db)

        assert result is True
        db.exec.assert_not_called()

    def test_returns_true_when_user_is_project_owner(self):
        user_id = uuid4()
        project_id = uuid4()
        db = MagicMock(spec=Session)
        mock_project = MagicMock()
        mock_project.owner_id = user_id
        db.exec.return_value.first.return_value = mock_project

        with patch(PATCH_HAS_PERMISSIONS, return_value=False):
            result = can_modify_project(user_id, project_id, db)

        assert result is True

    def test_returns_false_when_user_is_not_project_owner(self):
        user_id = uuid4()
        project_id = uuid4()
        db = MagicMock(spec=Session)
        mock_project = MagicMock()
        mock_project.owner_id = uuid4()
        db.exec.return_value.first.return_value = mock_project

        with patch(PATCH_HAS_PERMISSIONS, return_value=False):
            result = can_modify_project(user_id, project_id, db)

        assert result is False

    def test_returns_false_when_project_not_found(self):
        user_id = uuid4()
        project_id = uuid4()
        db = MagicMock(spec=Session)
        db.exec.return_value.first.return_value = None

        with patch(PATCH_HAS_PERMISSIONS, return_value=False):
            result = can_modify_project(user_id, project_id, db)

        assert result is False

    def test_returns_false_on_database_exception(self):
        user_id = uuid4()
        project_id = uuid4()
        db = MagicMock(spec=Session)
        db.exec.side_effect = Exception("DB connection error")

        with patch(PATCH_HAS_PERMISSIONS, return_value=False):
            result = can_modify_project(user_id, project_id, db)

        assert result is False


class TestCanModifyModel:
    def test_returns_true_when_user_has_manage_projects_permission(self):
        user_id = uuid4()
        model_id = uuid4()
        db = MagicMock(spec=Session)

        with patch(PATCH_HAS_PERMISSIONS, return_value=True):
            result = can_modify_model(user_id, model_id, db)

        assert result is True
        db.exec.assert_not_called()

    def test_returns_false_when_model_not_found(self):
        user_id = uuid4()
        model_id = uuid4()
        db = MagicMock(spec=Session)
        db.exec.return_value.first.return_value = None

        with patch(PATCH_HAS_PERMISSIONS, return_value=False):
            result = can_modify_model(user_id, model_id, db)

        assert result is False

    def test_returns_false_when_model_has_no_project_id(self):
        user_id = uuid4()
        model_id = uuid4()
        db = MagicMock(spec=Session)
        mock_model = MagicMock()
        mock_model.project_id = None
        db.exec.return_value.first.return_value = mock_model

        with patch(PATCH_HAS_PERMISSIONS, return_value=False):
            result = can_modify_model(user_id, model_id, db)

        assert result is False

    def test_returns_true_when_can_modify_project_returns_true(self):
        user_id = uuid4()
        model_id = uuid4()
        mock_project_id = uuid4()
        db = MagicMock(spec=Session)
        mock_model = MagicMock()
        mock_model.project_id = mock_project_id
        db.exec.return_value.first.return_value = mock_model

        with patch(PATCH_HAS_PERMISSIONS, return_value=False), \
             patch(PATCH_CAN_MODIFY_PROJECT, return_value=True) as mock_cmp:
            result = can_modify_model(user_id, model_id, db)

        assert result is True
        mock_cmp.assert_called_once_with(user_id, mock_project_id, db)

    def test_returns_false_when_can_modify_project_returns_false(self):
        user_id = uuid4()
        model_id = uuid4()
        mock_project_id = uuid4()
        db = MagicMock(spec=Session)
        mock_model = MagicMock()
        mock_model.project_id = mock_project_id
        db.exec.return_value.first.return_value = mock_model

        with patch(PATCH_HAS_PERMISSIONS, return_value=False), \
             patch(PATCH_CAN_MODIFY_PROJECT, return_value=False) as mock_cmp:
            result = can_modify_model(user_id, model_id, db)

        assert result is False
        mock_cmp.assert_called_once_with(user_id, mock_project_id, db)

    def test_returns_false_on_database_exception(self):
        user_id = uuid4()
        model_id = uuid4()
        db = MagicMock(spec=Session)
        db.exec.side_effect = Exception("DB connection error")

        with patch(PATCH_HAS_PERMISSIONS, return_value=False):
            result = can_modify_model(user_id, model_id, db)

        assert result is False
