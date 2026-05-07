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

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import Session

from flip_api.auth.dependencies import verify_token
from flip_api.db.database import get_session
from flip_api.domain.interfaces.user import IRegisterUser, IRegisterUserDto, IRoles
from flip_api.user_services.delete_user import delete_user
from flip_api.user_services.register_user import register_user
from flip_api.user_services.set_user_roles import set_user_roles
from flip_api.utils.logger import logger

router = APIRouter(prefix="/step", tags=["step_functions_services"])


@router.post("/users", response_model=IRegisterUserDto, status_code=status.HTTP_201_CREATED)
def register_user_step_function_endpoint(
    request: Request,
    user_data: IRegisterUser,
    db: Session = Depends(get_session),
    token_id: UUID = Depends(verify_token),
):
    """
    Register a new user and assign roles.

    Two-phase: register the Cognito user, then assign roles. If role
    assignment fails *definitively* (4xx, or unexpected Exception), the
    Cognito user is rolled back via ``delete_user``. If role assignment
    fails *transiently* (HTTP 503 — e.g. Cognito read could not verify the
    user exists), the rollback is skipped: the user has been registered
    and the operator can retry role assignment later. This avoids
    destroying valid registrations on a transient Cognito blip.

    Args:
        request (Request): The FastAPI request object.
        user_data (IRegisterUser): The user data to register, including email and roles.
        db (Session): The database session.
        token_id (UUID): The ID of the current user making the request.

    Returns:
        IRegisterUserDto: A DTO with the new user's id, email, and roles.

    Raises:
        HTTPException: If an error occurs during registration or role assignment.
    """
    try:
        # Step 1: Register User
        logger.info(f"Registering user: {user_data.email}")

        register_response = register_user(
            user_data=user_data,
            request=request,
            db=db,
            token_id=token_id,
        )

        # If the above does not raise an exception, we assume registration was successful

        # Extract user ID and roles
        user_id = register_response.user_id
        roles = IRoles(roles=register_response.roles)

        logger.info(f"Setting roles for user {user_id}: {roles}")

        try:
            # Set User Roles
            set_roles_response = set_user_roles(user_id=user_id, roles_data=roles, db=db, token_id=token_id)
            logger.info(f"Roles set successfully for user {user_id}: {set_roles_response}")

        except HTTPException as role_err:
            # 503 = transient Cognito-side read failure during the existence
            # check; role assignment never began. Don't tear down the
            # just-created user — surface 503 so the operator retries.
            if role_err.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
                logger.warning(
                    f"Role assignment for user {user_id} could not be verified "
                    f"(Cognito read transient); leaving user in place for retry."
                )
                raise

            # Definitive failure (4xx invalid roles, or anything non-503 5xx).
            # Roll back the Cognito user. delete_user drops any partial
            # user_role rows, writes an audit row, and removes the Cognito
            # user; it is idempotent on a missing Cognito sub.
            logger.exception(f"Failed to set user roles {roles} for user {user_id}; rolling back")
            try:
                delete_user(user_id=str(user_id), request=request, db=db, token_id=token_id)
            except Exception:
                # The rollback itself failed — surface the *original* error
                # to the caller, but log enough that an operator can clean
                # up the orphan Cognito user manually.
                logger.exception(
                    f"Failed to roll back user {user_id} ({user_data.email}) after role assignment "
                    f"failure; manual cleanup of Cognito + user_role required."
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        f"Failed to set user roles for user {user_id}; rollback also failed. "
                        f"Manual cleanup required."
                    ),
                ) from role_err

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to set user roles for user {user_id}. User has been deleted.",
            ) from role_err

        except Exception as role_err:
            logger.exception(f"Failed to set user roles {roles} for user {user_id}; rolling back")
            try:
                delete_user(user_id=str(user_id), request=request, db=db, token_id=token_id)
            except Exception:
                logger.exception(
                    f"Failed to roll back user {user_id} ({user_data.email}) after role assignment "
                    f"failure; manual cleanup of Cognito + user_role required."
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        f"Failed to set user roles for user {user_id}; rollback also failed. "
                        f"Manual cleanup required."
                    ),
                ) from role_err

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to set user roles for user {user_id}. User has been deleted.",
            ) from role_err

        # Step 7: Return the formatted output
        logger.info(f"User {user_id} registered successfully with roles {roles}")

        return IRegisterUserDto(
            user_id=user_id,
            email=register_response.email,
            roles=register_response.roles,
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.exception("Unhandled error in register_user_endpoint")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register user",
        ) from e
