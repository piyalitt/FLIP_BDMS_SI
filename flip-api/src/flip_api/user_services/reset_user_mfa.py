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

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import Session

from flip_api.auth.auth_utils import has_permissions
from flip_api.auth.dependencies import verify_token
from flip_api.db.database import get_session
from flip_api.db.models.user_models import PermissionRef
from flip_api.utils.cognito_helpers import get_user_pool_id, get_username, reset_user_mfa
from flip_api.utils.logger import logger

router = APIRouter(prefix="/users", tags=["user_services"])


@router.post("/{user_id}/mfa/reset", response_model=dict[str, Any])
def reset_mfa_for_user(
    user_id: str,
    request: Request,
    db: Session = Depends(get_session),
    token_id: UUID = Depends(verify_token),
) -> dict[str, Any]:
    """
    Reset (disable) a user's TOTP MFA preference.

    Used by administrators to recover users who have lost their authenticator
    device. The next sign-in attempt by the target user will return the
    ``CONTINUE_SIGN_IN_WITH_TOTP_SETUP`` challenge, forcing re-enrollment.

    Args:
        user_id: ID (Cognito ``sub``) of the user whose MFA should be reset
        request: FastAPI request object
        db: Database session
        token_id: ID of the authenticated user performing the reset

    Returns:
        dict[str, Any]: Empty dictionary on success.

    Raises:
        HTTPException: If the caller lacks permission, the target user is not
        found, or the Cognito call fails.
    """
    try:
        if not has_permissions(token_id, [PermissionRef.CAN_MANAGE_USERS], db):
            logger.error(f"User with ID: {token_id} attempted to reset MFA without permission")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User with ID: {token_id} was unable to manage users",
            )

        user_pool_id = get_user_pool_id(request)
        username = get_username(user_id, user_pool_id)

        if not username:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} is not registered.",
            )

        reset_user_mfa(username, user_pool_id)

        return {}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resetting user MFA: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error: {str(e)}"
        )
