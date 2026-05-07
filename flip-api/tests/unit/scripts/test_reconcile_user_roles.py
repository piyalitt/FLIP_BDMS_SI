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

from flip_api.db.models.user_models import UserRole
from flip_api.domain.schemas.users import CognitoUser
from flip_api.scripts.reconcile_user_roles import main, reconcile


def _cognito_user(user_id: UUID, email: str = "x@example.com") -> CognitoUser:
    return CognitoUser(id=user_id, email=email, is_disabled=False)  # type: ignore[call-arg]


def test_reconcile_removes_only_rows_whose_user_id_is_not_in_cognito():
    """Rows with a Cognito match are kept; ghost rows are removed."""
    keep_id = uuid4()
    ghost_id = uuid4()

    role_id = uuid4()
    rows = [
        UserRole(user_id=keep_id, role_id=role_id),
        UserRole(user_id=ghost_id, role_id=role_id),
    ]

    session = MagicMock()
    session.exec.return_value.all.return_value = rows

    with patch(
        "flip_api.scripts.reconcile_user_roles.get_cognito_users",
        return_value=[_cognito_user(keep_id)],
    ):
        ghosts_found = reconcile(session, dry_run=False)

    assert ghosts_found == 1
    # Single bulk DELETE for the ghost ids, then commit.
    session.execute.assert_called_once()
    session.commit.assert_called_once()


def test_reconcile_dry_run_does_not_delete():
    """Dry-run only logs; no DB writes."""
    ghost_id = uuid4()
    rows = [UserRole(user_id=ghost_id, role_id=uuid4())]

    session = MagicMock()
    session.exec.return_value.all.return_value = rows

    with patch(
        "flip_api.scripts.reconcile_user_roles.get_cognito_users",
        return_value=[],
    ):
        ghosts_found = reconcile(session, dry_run=True)

    assert ghosts_found == 1
    session.execute.assert_not_called()
    session.commit.assert_not_called()


def test_reconcile_no_ghosts_no_writes():
    """When every user_role row matches a Cognito sub, no DELETE runs."""
    keep_id = uuid4()
    rows = [UserRole(user_id=keep_id, role_id=uuid4())]

    session = MagicMock()
    session.exec.return_value.all.return_value = rows

    with patch(
        "flip_api.scripts.reconcile_user_roles.get_cognito_users",
        return_value=[_cognito_user(keep_id)],
    ):
        ghosts_found = reconcile(session, dry_run=False)

    assert ghosts_found == 0
    session.execute.assert_not_called()
    session.commit.assert_not_called()


def test_reconcile_refuses_to_delete_when_cognito_returns_empty():
    """Safety bail: empty Cognito + ghosts + non-dry-run must NOT delete.

    A zero-result Cognito list is almost certainly a transient read failure
    rather than a genuinely empty pool; deleting every grant in response
    would be catastrophic.
    """
    ghost_id = uuid4()
    rows = [UserRole(user_id=ghost_id, role_id=uuid4())]

    session = MagicMock()
    session.exec.return_value.all.return_value = rows

    with patch(
        "flip_api.scripts.reconcile_user_roles.get_cognito_users",
        return_value=[],
    ):
        ghosts_found = reconcile(session, dry_run=False)

    assert ghosts_found == 1
    session.execute.assert_not_called()
    session.commit.assert_not_called()


@patch("flip_api.scripts.reconcile_user_roles.reconcile")
@patch("flip_api.scripts.reconcile_user_roles.Session")
def test_main_default_invokes_reconcile_in_destructive_mode(mock_session_cls, mock_reconcile):
    """Default CLI invocation passes ``dry_run=False`` and opens a Session against the engine."""
    session_instance = MagicMock()
    mock_session_cls.return_value.__enter__.return_value = session_instance

    with patch("sys.argv", ["reconcile_user_roles"]):
        main()

    mock_reconcile.assert_called_once_with(session_instance, dry_run=False)


@patch("flip_api.scripts.reconcile_user_roles.reconcile")
@patch("flip_api.scripts.reconcile_user_roles.Session")
def test_main_dry_run_flag_propagates_to_reconcile(mock_session_cls, mock_reconcile):
    """``--dry-run`` flips the kwarg passed into ``reconcile``."""
    session_instance = MagicMock()
    mock_session_cls.return_value.__enter__.return_value = session_instance

    with patch("sys.argv", ["reconcile_user_roles", "--dry-run"]):
        main()

    mock_reconcile.assert_called_once_with(session_instance, dry_run=True)
