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
from flip_api.utils.logger import logger

security = HTTPBearer()


def _decode_cognito_jwt(token: str) -> dict[str, Any]:
    """
    Verify a Cognito-issued JWT and return its claims.

    Performs the verification steps documented by AWS for Cognito user pool tokens:
    signature, expiry, issuer, token_use, and audience binding to this app client.

    Raises ``jwt.InvalidTokenError`` (or a subclass) on any validation failure.
    """
    settings = get_settings()
    aws_region = settings.AWS_REGION
    user_pool_id = settings.AWS_COGNITO_USER_POOL_ID
    app_client_id = settings.AWS_COGNITO_APP_CLIENT_ID
    issuer = f"https://cognito-idp.{aws_region}.amazonaws.com/{user_pool_id}"

    jwks_url = f"{issuer}/.well-known/jwks.json"
    jwks_client = PyJWKClient(jwks_url)
    signing_key = jwks_client.get_signing_key_from_jwt(token)

    payload: dict[str, Any] = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        issuer=issuer,
        options={
            # aud is validated manually below so we can also handle access tokens (which use client_id).
            # TODO(#344): drop ID-token support and validate aud directly via PyJWT once flip-ui sends access tokens.
            "verify_aud": False,
            "require": ["exp", "iss", "sub", "token_use"],
        },
    )

    token_use = payload.get("token_use")
    if token_use == "id":
        if payload.get("aud") != app_client_id:
            raise jwt.InvalidTokenError("Invalid audience")
    elif token_use == "access":
        if payload.get("client_id") != app_client_id:
            raise jwt.InvalidTokenError("Invalid client_id")
    else:
        raise jwt.InvalidTokenError(f"Unsupported token_use: {token_use!r}")

    return payload


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> UUID:
    """
    Uses PyJWT and PyJWKClient to verify credential token with AWS Cognito.

    Args:
        credentials (HTTPAuthorizationCredentials): The HTTP authorization credentials in the result of using
        `HTTPBearer` or `HTTPDigest` in a dependency.

    Returns:
        UUID: The user ID (sub claim) from the verified token.

    Raises:
        HTTPException: If token is invalid, expired, or verification fails.
    """
    token = credentials.credentials

    try:
        payload = _decode_cognito_jwt(token)

        user_id_str = payload.get("sub")
        try:
            user_id = UUID(str(user_id_str))
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user identifier format",
                headers={"WWW-Authenticate": "Bearer"},
            )

        logger.info(f"Token verified successfully for user: {user_id}")
        return user_id

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
