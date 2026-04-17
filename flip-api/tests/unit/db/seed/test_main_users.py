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

import pytest
from sqlmodel import Session

from flip_api.db.models.user_models import RoleRef
from flip_api.db.seed.main_users import seed_main_users
from flip_api.utils.constants import (
    ADMIN_EMAIL_1,
    ADMIN_EMAIL_2,
    ADMIN_EMAIL_3,
    OBSERVER_EMAIL,
    RESEARCHER_EMAIL,
)


@pytest.fixture
def mock_session():
    return MagicMock(spec=Session)


@patch("flip_api.db.seed.main_users.ensure_user_and_role")
@patch("flip_api.db.seed.main_users.logger")
def test_seed_main_users_calls_ensure_user_and_role(mock_logger, mock_ensure_user_and_role, mock_session):
    """Test that seed_main_users calls ensure_user_and_role for each admin, researcher, and observer."""
    seed_main_users(mock_session)

    assert mock_ensure_user_and_role.call_count == 5

    mock_ensure_user_and_role.assert_any_call(ADMIN_EMAIL_1, RoleRef.ADMIN, mock_session)
    mock_ensure_user_and_role.assert_any_call(ADMIN_EMAIL_2, RoleRef.ADMIN, mock_session)
    mock_ensure_user_and_role.assert_any_call(ADMIN_EMAIL_3, RoleRef.ADMIN, mock_session)
    mock_ensure_user_and_role.assert_any_call(RESEARCHER_EMAIL, RoleRef.RESEARCHER, mock_session)
    mock_ensure_user_and_role.assert_any_call(OBSERVER_EMAIL, RoleRef.OBSERVER, mock_session)

    # Logging verified
    mock_logger.debug.assert_called_with("Seeding main users...")
    mock_logger.info.assert_called_with("✅ Finished seeding main users.")


@patch("flip_api.db.seed.main_users.ensure_user_and_role")
@patch("flip_api.db.seed.main_users.logger")
def test_seed_main_users_propagates_errors(mock_logger, mock_ensure_user_and_role, mock_session):
    """Test that errors in ensure_user_and_role propagate up."""
    mock_ensure_user_and_role.side_effect = Exception("Cognito failure")

    with pytest.raises(Exception, match="Cognito failure"):
        seed_main_users(mock_session)

    # Should only have tried first user before raising
    mock_ensure_user_and_role.assert_called_once_with(ADMIN_EMAIL_1, RoleRef.ADMIN, mock_session)


@patch("flip_api.db.seed.main_users.ensure_user_and_role")
@patch("flip_api.db.seed.main_users.logger")
def test_seed_main_users_runs_all_when_each_succeeds(mock_logger, mock_ensure_user_and_role, mock_session):
    """Test that all users are seeded when ensure_user_and_role succeeds."""
    mock_ensure_user_and_role.return_value = None

    seed_main_users(mock_session)

    expected_calls = [
        (ADMIN_EMAIL_1, RoleRef.ADMIN, mock_session),
        (ADMIN_EMAIL_2, RoleRef.ADMIN, mock_session),
        (ADMIN_EMAIL_3, RoleRef.ADMIN, mock_session),
        (RESEARCHER_EMAIL, RoleRef.RESEARCHER, mock_session),
        (OBSERVER_EMAIL, RoleRef.OBSERVER, mock_session),
    ]
    actual_calls = [c.args for c in mock_ensure_user_and_role.call_args_list]
    assert actual_calls == expected_calls

    # Final log
    mock_logger.info.assert_called_with("✅ Finished seeding main users.")
