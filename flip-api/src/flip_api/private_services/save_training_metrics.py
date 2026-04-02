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

from flip_api.auth.access_manager import authenticate_trust, verify_trust_identity
from flip_api.db.database import get_session
from flip_api.domain.schemas.private import TrainingMetrics
from flip_api.model_services.services.model_service import validate_trusts
from flip_api.private_services.services.private_service import save_training_metrics
from flip_api.utils.logger import logger

router = APIRouter(tags=["private_services"])


# [#114] ✅
@router.post(
    "/model/{model_id}/metrics",
    summary="Save training metrics for a model from a specific trust.",
    status_code=status.HTTP_204_NO_CONTENT,  # Returns 204 No Content on success
    response_model=None,
)
def save_training_metrics_endpoint(
    model_id: UUID,
    training_metrics: TrainingMetrics,
    request: Request,
    db: Session = Depends(get_session),
    authenticated_trust: str = Depends(authenticate_trust),
) -> None:
    """
    Receives and saves training metrics for a given model ID and trust.

    Args:
        model_id (UUID): The unique identifier for the model.
        training_metrics (TrainingMetrics): The training metrics to be saved.
        request (Request): The FastAPI request object, used for logging and context.
        db (Session): Database session dependency.
        authenticated_trust (str): Authenticated trust name (validated by dependency).

    Returns:
        Response: HTTP 204 No Content on success, or appropriate error response.

    Raises:
        HTTPException: If the trust is not associated with the model.
        HTTPException: If an internal server error occurs during processing.
    """
    verify_trust_identity(training_metrics.trust, authenticated_trust)
    endpoint_path = request.url.path

    logger.debug(
        f"Received request to save training metrics for model {model_id} from trust {training_metrics.trust} via "
        f"{endpoint_path}"
    )

    try:
        if not validate_trusts(model_id=model_id, trusts=[training_metrics.trust], session=db):
            error_msg = f"The trust: {training_metrics.trust} is not associated with model: {model_id}"
            logger.error(error_msg)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)

        save_training_metrics(model_id=model_id, training_metrics=training_metrics, db=db)

    except HTTPException as http_exc:
        logger.warning(
            f"Service HTTPException for model {model_id}, trust {training_metrics.trust} "
            f"in {endpoint_path}: {http_exc.detail}"
        )
        raise http_exc
    except Exception as e:
        logger.error(
            f"Unhandled error processing training metrics for model {model_id}, trust {training_metrics.trust} "
            f"in {endpoint_path}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred while saving training metrics.",
        )
