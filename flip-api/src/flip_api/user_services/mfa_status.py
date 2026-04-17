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

from uuid import UUID

from fastapi import APIRouter, Depends, Request

from flip_api.auth.dependencies import verify_token_no_mfa
from flip_api.utils.cognito_helpers import get_user_pool_id, get_username, is_mfa_enabled

router = APIRouter(prefix="/users", tags=["user_services"])


@router.get("/me/mfa/status", response_model=dict[str, bool])
def get_own_mfa_status(
    request: Request,
    token_id: UUID = Depends(verify_token_no_mfa),
) -> dict[str, bool]:
    """
    Report whether the caller has an active TOTP authenticator.

    Exempt from the MFA gate so a freshly-invited or admin-reset user can
    discover their enrolment state and be routed to the setup page.

    Args:
        request: FastAPI request object, used to resolve the Cognito user
            pool id.
        token_id: ID of the authenticated user (from the bearer token).

    Returns:
        dict[str, bool]: ``{"enabled": True}`` if the caller has a verified
        and enabled TOTP device, ``{"enabled": False}`` otherwise.

    Raises:
        HTTPException: 404 if the token's sub does not resolve to a
        Cognito user, 500 on Cognito errors.
    """
    user_pool_id = get_user_pool_id(request)
    username = get_username(str(token_id), user_pool_id)
    return {"enabled": is_mfa_enabled(username, user_pool_id)}
