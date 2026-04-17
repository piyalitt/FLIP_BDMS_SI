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

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from flip_api.config import get_settings
from flip_api.utils.cognito_helpers import is_mfa_enabled
from flip_api.utils.logger import logger

security = HTTPBearer()
AWS_REGION = get_settings().AWS_REGION
USER_POOL_ID = get_settings().AWS_COGNITO_USER_POOL_ID


def _decode_verified_claims(token: str) -> dict[str, Any]:
    """
    Validate a Cognito JWT and return its verified claims.

    Args:
        token (str): The raw bearer token.

    Returns:
        dict[str, Any]: The decoded JWT payload.

    Raises:
        HTTPException: If token is invalid, expired, or wrong type.
    """
    try:
        jwks_url = f"https://cognito-idp.{AWS_REGION}.amazonaws.com/{USER_POOL_ID}/.well-known/jwks.json"
        jwks_client = PyJWKClient(jwks_url)
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=None,
            options={"verify_aud": False},
        )

        if payload.get("token_use") not in ["id", "access"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type. Expected ID token.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return payload

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        logger.error(f"Token validation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during token verification: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during authentication",
        )


def _extract_user_id(payload: dict[str, Any]) -> UUID:
    """Return the ``sub`` claim as a UUID, raising 401 on failure."""
    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing user identifier",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user identifier format",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _extract_username(payload: dict[str, Any]) -> str:
    """
    Return the Cognito Username claim (email in our pool).

    Access tokens carry it as ``username``; ID tokens as ``cognito:username``.

    Raises:
        HTTPException: If neither claim is present (401).
    """
    username = payload.get("username") or payload.get("cognito:username")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing username claim",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return str(username)


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> UUID:
    """
    Verify a Cognito JWT and enforce that the caller has TOTP MFA enabled.

    The MFA requirement is checked at the application boundary (rather than
    at the Cognito pool) so admin resets take effect immediately — see the
    comment on ``aws_cognito_user_pool.flip_user_pool`` in the cognito
    module for the full rationale. MFA-bootstrap endpoints use
    :func:`verify_token_no_mfa` instead.

    Args:
        credentials (HTTPAuthorizationCredentials): Bearer credentials from
            the incoming request.

    Returns:
        UUID: The user ID (``sub`` claim) from the verified token.

    Raises:
        HTTPException: 401 if the token is invalid, expired, or missing
            claims; 403 if the caller has not enrolled TOTP.
    """
    payload = _decode_verified_claims(credentials.credentials)
    user_id = _extract_user_id(payload)
    username = _extract_username(payload)

    if not is_mfa_enabled(username, USER_POOL_ID):
        logger.warning(f"User {user_id} hit MFA-gated route without active TOTP")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="MFA enrolment required",
        )

    logger.info(f"Token verified successfully for user: {user_id}")
    return user_id


def verify_token_no_mfa(credentials: HTTPAuthorizationCredentials = Depends(security)) -> UUID:
    """
    Verify a Cognito JWT without requiring TOTP MFA.

    Reserved for the MFA bootstrap endpoints (status check, enrolment
    helpers) that a freshly-reset or newly-invited user needs to reach
    before they have an active authenticator. Every other route must use
    :func:`verify_token`.

    Args:
        credentials (HTTPAuthorizationCredentials): Bearer credentials from
            the incoming request.

    Returns:
        UUID: The user ID (``sub`` claim) from the verified token.

    Raises:
        HTTPException: 401 if the token is invalid, expired, or missing
            claims.
    """
    payload = _decode_verified_claims(credentials.credentials)
    return _extract_user_id(payload)
