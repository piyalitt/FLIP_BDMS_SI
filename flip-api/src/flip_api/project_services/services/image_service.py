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

import base64
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, col, select, update

from flip_api.db.models.main_models import Trust as DBTrust
from flip_api.db.models.main_models import TrustTask, XNATProjectStatus
from flip_api.domain.interfaces.project import (
    IImagingStatus,
    IReimportQuery,
    IUpdateXnatProfile,
)
from flip_api.domain.schemas.projects import ImagingProject, XnatProjectStatusInfo
from flip_api.domain.schemas.status import TaskStatus, TaskType, XNATImageStatus
from flip_api.trusts_services.services.trust import get_trusts
from flip_api.utils.logger import logger


def to_utc_aware(dt: datetime | None) -> datetime:
    """Convert a datetime to a timezone-aware UTC datetime. If the input is None, returns the minimum datetime."""
    if dt is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


# Helper for Base64 URL encoding
def base64_url_encode(data: str) -> str:
    """Encode a string using Base64 URL encoding without padding."""
    return base64.urlsafe_b64encode(data.encode("utf-8")).decode("utf-8").rstrip("=")


def get_imaging_projects(project_id: UUID, db: Session) -> list[ImagingProject]:
    """
    Retrieve imaging projects associated with a given project ID.

    Args:
        project_id (UUID): The ID of the project to retrieve imaging projects for.
        db (Session): The database session for executing queries.

    Returns:
        List[ImagingProject]: A list of ImagingProject objects associated with the given project ID.

    Raises:
        SQLAlchemyError: If there is an error executing the database query.
        Exception: If there is an unexpected error during the retrieval process.
    """
    try:
        # Columns must match the order expected by ImagingProject constructor or mapping logic
        statement = (
            select(  # type: ignore[call-overload]
                XNATProjectStatus.id,
                XNATProjectStatus.xnat_project_id,
                XNATProjectStatus.trust_id,
                XNATProjectStatus.retrieve_image_status,
                DBTrust.name,
                XNATProjectStatus.reimport_count,
            )
            .join(DBTrust, col(XNATProjectStatus.trust_id) == DBTrust.id)
            .where(col(XNATProjectStatus.project_id) == project_id)
        )
        results = db.exec(statement).all()
        logger.debug(f"Imaging projects fetched for project_id {project_id}: {results}")

        imaging_projects = [
            ImagingProject(
                id=row[0],
                xnat_project_id=row[1],
                trust_id=row[2],
                retrieve_image_status=XNATImageStatus(row[3]),
                name=row[4],
                reimport_count=row[5],
            )
            for row in results
        ]
        return imaging_projects
    except SQLAlchemyError as e:
        logger.error(f"Database error fetching imaging projects for project_id {project_id}: {e}", exc_info=True)
        raise
    except Exception as e:  # Catch other unexpected errors
        logger.error(f"Unexpected error fetching imaging projects for project_id {project_id}: {e}", exc_info=True)
        raise


def delete_imaging_project(imaging_project: ImagingProject, db: Session) -> bool:
    """
    Queue a task to delete an imaging project and update its status in the database.

    Args:
        imaging_project (ImagingProject): The imaging project to delete.
        db (Session): The database session for executing queries.

    Returns:
        bool: True if the task was queued and status updated successfully, False otherwise.
    """
    try:
        # Queue deletion task for the trust
        task = TrustTask(
            trust_id=imaging_project.trust_id,
            task_type=TaskType.DELETE_IMAGING,
            payload=json.dumps({"imaging_project_id": str(imaging_project.xnat_project_id)}),
        )
        db.add(task)

        statement = (
            update(XNATProjectStatus)
            .where(col(XNATProjectStatus.id) == imaging_project.id)
            .values(retrieve_image_status=XNATImageStatus.DELETED.value)
        )
        db.execute(statement)
        db.commit()
        logger.info(
            f"Queued deletion task and marked imaging project {imaging_project.xnat_project_id} "
            f"(ID: {imaging_project.id}) as DELETED."
        )
        return True
    except Exception as e:
        logger.error(f"Error queuing imaging project deletion: {e}", exc_info=True)
        db.rollback()
        return False


def get_xnat_project_status_info(xnat_project_id: UUID, db: Session) -> XnatProjectStatusInfo | None:
    """
    Retrieve the XNAT project status information for a given XNAT project ID.

    Args:
        xnat_project_id (UUID): The ID of the XNAT project to retrieve status information for.
        db (Session): The database session for executing queries.

    Returns:
        Optional[XnatProjectStatusInfo]: An object containing the XNAT project status information, or None if the
                                         project status could not be found.

    Raises:
        SQLAlchemyError: If there is an error executing the database query.
        Exception: If there is an unexpected error during the retrieval process.
    """
    try:
        statement = select(XNATProjectStatus.retrieve_image_status, XNATProjectStatus.reimport_count).where(
            XNATProjectStatus.xnat_project_id == xnat_project_id
        )

        result_row = db.exec(statement).one_or_none()

        if not result_row:
            logger.error(f"Could not get XNAT status for project id: {xnat_project_id}")
            return None

        return XnatProjectStatusInfo(retrieve_image_status=XNATImageStatus(result_row[0]), reimport_count=result_row[1])
    except SQLAlchemyError as e:
        logger.error(f"Database error fetching XNAT project status for {xnat_project_id}: {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching XNAT project status for {xnat_project_id}: {e}", exc_info=True)
        raise


def get_imaging_project_statuses(
    imaging_projects: list[ImagingProject], encoded_query: str, db: Session
) -> list[IImagingStatus]:
    """
    Retrieve the imaging project statuses from local DB and queue status refresh tasks for trusts.

    Instead of making direct HTTP calls to each trust, this returns locally cached status
    and queues GET_IMAGING_STATUS tasks for each trust to report back updated status.

    Args:
        imaging_projects (List[ImagingProject]): The list of imaging projects to retrieve statuses for.
        encoded_query (str): The Base64 URL encoded query.
        db (Session): The database session for executing queries.

    Returns:
        List[IImagingStatus]: A list of IImagingStatus containing the cached status for each imaging project.
    """
    logger.debug(
        f"Attempting to retrieve the imaging project status. Trusts requested: {[ip.name for ip in imaging_projects]}"
    )
    response_statuses: list[IImagingStatus] = []

    for row_project in imaging_projects:
        xnat_status_info = get_xnat_project_status_info(row_project.xnat_project_id, db)
        logger.debug(f"Retrieved XNAT status info for project {row_project.xnat_project_id}: {xnat_status_info}")

        project_creation_completed = False
        reimport_count_val = 0
        if xnat_status_info:
            project_creation_completed = xnat_status_info.retrieve_image_status == XNATImageStatus.CREATED
            reimport_count_val = xnat_status_info.reimport_count

        current_project_status = IImagingStatus(
            trust_id=row_project.trust_id,
            trust_name=row_project.name,
            project_creation_completed=project_creation_completed,
            reimport_count=reimport_count_val,
            import_status=None,
        )  # type: ignore[call-arg]

        # Queue a status refresh task only if one isn't already pending
        existing_task = db.exec(
            select(TrustTask)
            .where(TrustTask.trust_id == row_project.trust_id)
            .where(TrustTask.task_type == TaskType.GET_IMAGING_STATUS)
            .where(TrustTask.status == TaskStatus.PENDING)
        ).first()
        if not existing_task:
            task = TrustTask(
                trust_id=row_project.trust_id,
                task_type=TaskType.GET_IMAGING_STATUS,
                payload=json.dumps({
                    "imaging_project_id": str(row_project.xnat_project_id),
                    "encoded_query": encoded_query,
                }),
            )
            db.add(task)

        response_statuses.append(current_project_status)

    db.commit()

    if response_statuses:
        logger.info(f"Imaging statuses retrieved from DB: {len(response_statuses)} trusts. Refresh tasks queued.")
    else:
        logger.error("No imaging projects found. An empty list will be returned")

    return response_statuses


def update_xnat_user_profile(
    request_data: IUpdateXnatProfile,
    db: Session,
) -> None:
    """
    Queue user profile update tasks for all trusts' XNAT instances.

    Args:
        request_data (IUpdateXnatProfile): The user profile data to update.
        db (Session): The database session for retrieving trust information.

    Returns:
        None
    """
    logger.debug(f"Queuing XNAT user profile update for: {request_data.email} at all trusts")

    trusts = get_trusts(db)

    if not trusts:
        logger.error("No trusts found to queue user profile update tasks.")
        return

    for trust in trusts:
        task = TrustTask(
            trust_id=trust.id,
            task_type=TaskType.UPDATE_USER_PROFILE,
            payload=json.dumps(request_data.model_dump(mode="json")),
        )
        db.add(task)

    db.commit()
    logger.info(f"Queued user profile update tasks for {len(trusts)} trusts")


def reimport_failed_studies(
    reimport_queries: list[IReimportQuery],
    db: Session,
    project_reimport_rate_minutes: int,
) -> bool:
    """
    Queue reimport tasks for failed studies, ensuring that reimports are only attempted if the
    specified time interval has passed since the last reimport.

    Args:
        reimport_queries (List[IReimportQuery]): A list of queries containing information about which projects and
            trusts to reimport studies for, along with the last reimport time.
        db (Session): The database session for updating reimport status.
        project_reimport_rate_minutes (int): The minimum number of minutes that must have passed since the last
            reimport before attempting another reimport for the same project and trust.

    Returns:
        bool: True if all eligible reimport tasks were queued successfully.
    """
    total_eligible_queries = 0
    queued_count = 0

    for query in reimport_queries:
        encoded_query = base64_url_encode(query.query)

        last_reimport_time_utc = to_utc_aware(query.last_reimport)
        reimport_interval = timedelta(minutes=project_reimport_rate_minutes)

        now_utc = datetime.now(timezone.utc)
        next_eligible = last_reimport_time_utc + reimport_interval
        if now_utc <= next_eligible:
            logger.info(
                "Time specified in PROJECT_REIMPORT_RATE has not been exceeded for project "
                f"{query.xnat_project_id} at trust {query.trust_name} "
                f"(Last reimport: {last_reimport_time_utc}, Next eligible: {next_eligible})"
            )
            continue

        total_eligible_queries += 1

        try:
            # Queue reimport task for the trust
            task = TrustTask(
                trust_id=query.trust_id,
                task_type=TaskType.REIMPORT_STUDIES,
                payload=json.dumps({
                    "imaging_project_id": str(query.xnat_project_id),
                    "encoded_query": encoded_query,
                }),
            )
            db.add(task)

            # Update the last_reimport and increment reimport_count in the database
            xnat_project_status = db.exec(
                select(XNATProjectStatus)
                .where(XNATProjectStatus.trust_id == query.trust_id)
                .where(XNATProjectStatus.xnat_project_id == query.xnat_project_id)
            ).one_or_none()

            if xnat_project_status:
                xnat_project_status.last_reimport = datetime.now(timezone.utc)
                xnat_project_status.reimport_count += 1
                queued_count += 1
            else:
                logger.error(
                    f"Could not find XNATProjectStatus record to update for project {query.xnat_project_id} "
                    f"at trust {query.trust_name}"
                )
                continue

        except Exception as error:
            logger.error(
                "There was an unexpected error when queuing reimport for project %s at trust %s: %s",
                query.xnat_project_id,
                query.trust_name,
                error,
                exc_info=True,
            )
            continue

    db.commit()

    if total_eligible_queries == 0:
        logger.info("No queries were eligible for reimport at this time.")
        return True

    if queued_count < total_eligible_queries:
        logger.error(f"Not all eligible reimport tasks were queued: {queued_count}/{total_eligible_queries}")
        return False

    logger.info(f"Reimport tasks queued: {queued_count}/{total_eligible_queries}")
    return True
