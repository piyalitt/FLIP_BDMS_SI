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

"""
Task handlers for processing tasks received from the central hub via polling.

Each handler processes a specific task type and returns a result dict.
"""

import json
from typing import Any

from trust_api.config import get_settings
from trust_api.routers.schemas import (
    CentralHubProject,
    CohortQueryInput,
    DeleteImagingInput,
    GetImagingStatusInput,
    ReimportStudiesInput,
    UpdateProfileRequest,
)
from trust_api.utils.http import make_request
from trust_api.utils.logger import logger

DATA_ACCESS_API_URL = get_settings().DATA_ACCESS_API_URL
CENTRAL_HUB_API_URL = get_settings().CENTRAL_HUB_API_URL
IMAGING_API_URL = get_settings().IMAGING_API_URL
PRIVATE_API_KEY = get_settings().PRIVATE_API_KEY
PRIVATE_API_KEY_HEADER = get_settings().PRIVATE_API_KEY_HEADER


async def handle_cohort_query(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Process a cohort query task.

    Calls the local data-access-api, then pushes results back to the central hub.

    Args:
        payload: Task payload containing query details (query, query_name, encrypted_project_id, etc.)

    Returns:
        dict with success status and any error details.
    """
    logger.info(f"Processing cohort query task: query_id={payload.get('query_id')}")

    try:
        CohortQueryInput(**payload)
        # Post cohort query to the local data access API
        response = await make_request(
            method="POST",
            url=f"{DATA_ACCESS_API_URL}/cohort",
            json_body=payload,
        )

        # Convert all 'value' fields to strings before sending
        for group in response.get("data", []):  # type: ignore[union-attr]
            for result in group.get("results", []):  # type: ignore[union-attr, attr-defined]
                if "value" in result:
                    result["value"] = str(result["value"])

        # Send results back to the central hub
        await make_request(
            method="POST",
            url=f"{CENTRAL_HUB_API_URL}/cohort/results",
            json_body=response,
            headers={PRIVATE_API_KEY_HEADER: PRIVATE_API_KEY},
        )

        logger.info(f"Cohort query completed: query_id={payload.get('query_id')}")
        return {"success": True}

    except Exception as e:
        logger.error(f"Error processing cohort query: {e}")
        return {"success": False, "error": str(e)}


async def handle_create_imaging(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Process an imaging project creation task.

    Calls the local imaging-api to create the project.

    Args:
        payload: Task payload containing project details.

    Returns:
        dict with success status and imaging project result.
    """
    logger.info(f"Processing create imaging task: project_id={payload.get('project_id')}")

    try:
        CentralHubProject(**payload)
        response = await make_request(
            method="POST",
            url=f"{IMAGING_API_URL}/projects/create-project-from-central-hub-project",
            json_body=payload,
        )

        logger.info(f"Imaging project created: {response}")
        return {"success": True, "result": json.dumps(response)}

    except Exception as e:
        logger.error(f"Error creating imaging project: {e}")
        return {"success": False, "error": str(e)}


async def handle_delete_imaging(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Process an imaging project deletion task.

    Args:
        payload: Task payload containing imaging_project_id.

    Returns:
        dict with success status.
    """
    logger.info(f"Processing delete imaging task: {payload.get('imaging_project_id')}")

    try:
        validated = DeleteImagingInput(**payload)
        imaging_project_id = validated.imaging_project_id
        await make_request(
            method="DELETE",
            url=f"{IMAGING_API_URL}/projects/",
            params={"project_id": imaging_project_id},
        )

        logger.info(f"Imaging project deleted: {imaging_project_id}")
        return {"success": True}

    except Exception as e:
        logger.error(f"Error deleting imaging project: {e}")
        return {"success": False, "error": str(e)}


async def handle_get_imaging_status(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Process an imaging status retrieval task.

    Gets the import status from the local imaging-api and reports back to the hub.

    Args:
        payload: Task payload containing imaging_project_id and encoded_query.

    Returns:
        dict with success status and imaging status result.
    """
    logger.info(f"Processing get imaging status task: {payload.get('imaging_project_id')}")

    try:
        validated = GetImagingStatusInput(**payload)
        imaging_project_id = validated.imaging_project_id
        encoded_query = validated.encoded_query
        response = await make_request(
            method="GET",
            url=f"{IMAGING_API_URL}/retrieval/import_status_count/{imaging_project_id}",
            params={"encoded_query": encoded_query},
        )

        logger.info(f"Imaging status retrieved: {imaging_project_id}")
        return {"success": True, "result": json.dumps(response)}

    except Exception as e:
        logger.error(f"Error getting imaging status: {e}")
        return {"success": False, "error": str(e)}


async def handle_reimport_studies(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Process a reimport studies task.

    Args:
        payload: Task payload containing imaging_project_id and encoded_query.

    Returns:
        dict with success status.
    """
    logger.info(f"Processing reimport studies task: {payload.get('imaging_project_id')}")

    try:
        validated = ReimportStudiesInput(**payload)
        imaging_project_id = validated.imaging_project_id
        encoded_query = validated.encoded_query
        await make_request(
            method="PUT",
            url=f"{IMAGING_API_URL}/retrieval/reimport_imaging_project_studies/{imaging_project_id}",
            params={"encoded_query": encoded_query},
        )

        logger.info(f"Reimport initiated: {imaging_project_id}")
        return {"success": True}

    except Exception as e:
        logger.error(f"Error reimporting studies: {e}")
        return {"success": False, "error": str(e)}


async def handle_update_user_profile(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Process a user profile update task.

    Args:
        payload: Task payload containing email and enabled fields.

    Returns:
        dict with success status.
    """
    logger.info(f"Processing update user profile task: email={payload.get('email')}")

    try:
        UpdateProfileRequest(**payload)
        await make_request(
            method="PUT",
            url=f"{IMAGING_API_URL}/users",
            json_body=payload,
        )

        logger.info(f"User profile updated: {payload.get('email')}")
        return {"success": True}

    except Exception as e:
        logger.error(f"Error updating user profile: {e}")
        return {"success": False, "error": str(e)}


# Registry mapping task types to their handlers
TASK_HANDLERS = {
    "cohort_query": handle_cohort_query,
    "create_imaging": handle_create_imaging,
    "delete_imaging": handle_delete_imaging,
    "get_imaging_status": handle_get_imaging_status,
    "reimport_studies": handle_reimport_studies,
    "update_user_profile": handle_update_user_profile,
}
