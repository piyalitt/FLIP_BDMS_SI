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
from uuid import uuid4

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from flip_api.domain.interfaces.user import IUserResponse
from flip_api.main import app
from flip_api.step_functions_services.register_user_step_function import (
    get_session,
    verify_token,
)

client = TestClient(app)


@pytest.fixture
def user_payload():
    return {
        "email": "test@example.com",
        "roles": [str(uuid4()), str(uuid4())],
    }


@pytest.fixture
def mock_register_response(user_payload):
    return IUserResponse(user_id=uuid4(), email=user_payload["email"], roles=user_payload["roles"])


@pytest.fixture(autouse=True)
def override_dependencies():
    mock_session = MagicMock()
    user_id = uuid4()

    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[verify_token] = lambda: user_id

    yield mock_session, user_id

    app.dependency_overrides = {}


@patch("flip_api.step_functions_services.register_user_step_function.set_user_roles")
@patch("flip_api.step_functions_services.register_user_step_function.register_user")
def test_register_user_success(mock_register, mock_set_roles, user_payload, mock_register_response):
    mock_register.return_value = mock_register_response
    mock_set_roles.return_value = user_payload["roles"]

    response = client.post("/api/step/users", json=user_payload)

    assert response.status_code == 201
    data = response.json()
    print(data)
    assert data["email"] == user_payload["email"]
    assert data["roles"] == user_payload["roles"]

    mock_register.assert_called_once()
    mock_set_roles.assert_called_once()


@patch("flip_api.step_functions_services.register_user_step_function.delete_user")
@patch("flip_api.step_functions_services.register_user_step_function.set_user_roles")
@patch("flip_api.step_functions_services.register_user_step_function.register_user")
def test_register_user_role_assignment_fails(
    mock_register, mock_set_roles, mock_delete_user, user_payload, mock_register_response
):
    mock_register.return_value = mock_register_response

    # Simulate failure in setting roles
    mock_set_roles.side_effect = Exception("Role assignment error")

    response = client.post("/api/step/users", json=user_payload)

    assert response.status_code == 500
    assert (
        "Failed to register user" in response.json()["detail"]
        or "Failed to set user roles" in response.json()["detail"]
    )

    mock_register.assert_called_once()
    mock_set_roles.assert_called_once()
    mock_delete_user.assert_called_once()


@patch("flip_api.step_functions_services.register_user_step_function.register_user")
def test_register_user_unexpected_exception(mock_register, user_payload):
    mock_register.side_effect = Exception("DB failure")

    response = client.post("/api/step/users", json=user_payload)

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to register user"
    # Sanity: the inner exception text isn't echoed back to the client.
    assert "DB failure" not in response.json()["detail"]

    mock_register.assert_called_once()


@patch("flip_api.step_functions_services.register_user_step_function.delete_user")
@patch("flip_api.step_functions_services.register_user_step_function.set_user_roles")
@patch("flip_api.step_functions_services.register_user_step_function.register_user")
def test_role_assignment_503_does_not_roll_back(
    mock_register, mock_set_roles, mock_delete_user, user_payload, mock_register_response
):
    """A 503 from set_user_roles signals a transient Cognito read failure during the
    existence check. The just-created user must NOT be torn down — the operator can
    retry role assignment once Cognito recovers.
    """
    mock_register.return_value = mock_register_response
    mock_set_roles.side_effect = HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Could not verify user existence in Cognito; please try again.",
    )

    response = client.post("/api/step/users", json=user_payload)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    # Critical: the rollback was NOT performed — we'd be destroying a valid registration.
    mock_delete_user.assert_not_called()


@patch("flip_api.step_functions_services.register_user_step_function.delete_user")
@patch("flip_api.step_functions_services.register_user_step_function.set_user_roles")
@patch("flip_api.step_functions_services.register_user_step_function.register_user")
def test_rollback_failure_surfaces_manual_cleanup_message(
    mock_register, mock_set_roles, mock_delete_user, user_payload, mock_register_response
):
    """If the rollback delete_user itself raises, surface a 500 that names the orphan
    state explicitly so an operator can clean up — and don't mask it as a generic error.
    """
    mock_register.return_value = mock_register_response
    mock_set_roles.side_effect = Exception("Definitive role assignment failure")
    mock_delete_user.side_effect = Exception("Cognito delete also failed")

    response = client.post("/api/step/users", json=user_payload)

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    detail = response.json()["detail"]
    assert "rollback also failed" in detail.lower()
    assert "manual cleanup" in detail.lower()
    mock_delete_user.assert_called_once()
