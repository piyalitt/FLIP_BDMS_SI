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
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from flip_api.domain.interfaces.project import (
    IReimportQuery,
    IUpdateXnatProfile,
)
from flip_api.domain.interfaces.trust import ITrust
from flip_api.domain.schemas.projects import (
    ImagingProject,
    XnatProjectStatusInfo,
)
from flip_api.domain.schemas.status import XNATImageStatus
from flip_api.project_services.services.image_service import (
    delete_imaging_project,
    get_imaging_project_statuses,
    get_imaging_projects,
    get_xnat_project_status_info,
    reimport_failed_studies,
    update_xnat_user_profile,
)

# Mocking paths
MOCK_SERVICE_PATH = "flip_api.project_services.services.image_service"
MOCK_LOGGER_PATH = f"{MOCK_SERVICE_PATH}.logger"
MOCK_GET_TRUSTS_PATH = f"{MOCK_SERVICE_PATH}.get_trusts"


@pytest.fixture
def sample_project_id() -> str:
    return str(uuid4())


@pytest.fixture
def sample_imaging_project_data(sample_project_id: str) -> ImagingProject:
    return ImagingProject(
        id=uuid4(),
        xnat_project_id=uuid4(),
        trust_id=uuid4(),
        retrieve_image_status=XNATImageStatus.CREATED,
        name="Test Trust XNAT",
        reimport_count=0,
    )


# --- get_imaging_projects ---
class TestGetImagingProjects:
    def test_success(self, mock_db_session: MagicMock, sample_project_id: UUID):
        db_row_data = [
            (uuid4(), uuid4(), uuid4(), "CREATED", "Trust XNAT 1", 0),
            (uuid4(), uuid4(), uuid4(), "DELETED", "Trust XNAT 2", 1),
        ]
        # Simulate db.exec(statement).all() returning list of tuples/rows
        mock_db_session.exec.return_value.all.return_value = db_row_data

        result = get_imaging_projects(sample_project_id, mock_db_session)

        assert len(result) == 2
        assert isinstance(result[0], ImagingProject)
        assert result[0].id == db_row_data[0][0]
        assert result[0].xnat_project_id == db_row_data[0][1]
        assert result[0].trust_id == db_row_data[0][2]
        assert result[0].retrieve_image_status == XNATImageStatus(db_row_data[0][3])
        assert result[0].name == db_row_data[0][4]
        assert result[0].reimport_count == db_row_data[0][5]

        mock_db_session.exec.assert_called_once()

    @patch(MOCK_LOGGER_PATH)
    def test_db_error(self, mock_logger: MagicMock, mock_db_session: MagicMock, sample_project_id: UUID):
        db_error = Exception("DB Read Error")
        mock_db_session.exec.side_effect = db_error
        with pytest.raises(Exception, match="DB Read Error"):
            get_imaging_projects(sample_project_id, mock_db_session)
        mock_logger.error.assert_called_once()


# --- delete_imaging_project ---
class TestDeleteImagingProject:
    @patch(MOCK_LOGGER_PATH)
    def test_success(
        self,
        mock_logger: MagicMock,
        mock_db_session: MagicMock,
        sample_imaging_project_data: ImagingProject,
    ):
        result = delete_imaging_project(sample_imaging_project_data, mock_db_session)

        assert result is True
        # Should add a TrustTask and update status
        mock_db_session.add.assert_called_once()
        mock_db_session.execute.assert_called_once()
        mock_db_session.commit.assert_called_once()

    @patch(MOCK_LOGGER_PATH)
    def test_db_update_fails(
        self,
        mock_logger: MagicMock,
        mock_db_session: MagicMock,
        sample_imaging_project_data: ImagingProject,
    ):
        db_update_error = Exception("DB Update Failed")
        mock_db_session.execute.side_effect = db_update_error

        result = delete_imaging_project(sample_imaging_project_data, mock_db_session)

        assert result is False
        mock_logger.error.assert_called_with(
            f"Error queuing imaging project deletion: {db_update_error}", exc_info=True
        )
        mock_db_session.rollback.assert_called_once()
        mock_db_session.commit.assert_not_called()


# --- get_xnat_project_status_info ---
class TestGetXnatProjectStatusInfo:
    def test_success(self, mock_db_session: MagicMock):
        xnat_id = uuid4()
        db_row = (XNATImageStatus.CREATED, 1)  # retrieve_image_status, reimport_count
        mock_db_session.exec.return_value.one_or_none.return_value = db_row

        result = get_xnat_project_status_info(xnat_id, mock_db_session)

        assert isinstance(result, XnatProjectStatusInfo)
        assert result.retrieve_image_status == XNATImageStatus.CREATED
        assert result.reimport_count == 1
        mock_db_session.exec.assert_called_once()

    @patch(MOCK_LOGGER_PATH)
    def test_not_found(self, mock_logger: MagicMock, mock_db_session: MagicMock):
        xnat_id = uuid4()
        mock_db_session.exec.return_value.one_or_none.return_value = None

        result = get_xnat_project_status_info(xnat_id, mock_db_session)

        assert result is None
        mock_logger.error.assert_called_with(f"Could not get XNAT status for project id: {xnat_id}")

    @patch(MOCK_LOGGER_PATH)
    def test_db_error(self, mock_logger: MagicMock, mock_db_session: MagicMock):
        xnat_id = uuid4()
        db_error = Exception("DB Error")
        mock_db_session.exec.side_effect = db_error

        with pytest.raises(Exception, match="DB Error"):
            get_xnat_project_status_info(xnat_id, mock_db_session)
        mock_logger.error.assert_called_with(
            f"Unexpected error fetching XNAT project status for {xnat_id}: {db_error}", exc_info=True
        )


# --- get_imaging_project_statuses ---
class TestGetImagingProjectStatuses:
    @patch(f"{MOCK_SERVICE_PATH}.get_xnat_project_status_info")
    @patch(MOCK_LOGGER_PATH)
    def test_returns_statuses_and_queues_tasks(
        self,
        mock_logger: MagicMock,
        mock_get_xnat_status: MagicMock,
        mock_db_session: MagicMock,
    ):
        trust_id_1, trust_id_2 = uuid4(), uuid4()
        imaging_projects_list = [
            ImagingProject(
                id=uuid4(),
                xnat_project_id=uuid4(),
                trust_id=trust_id_1,
                retrieve_image_status=XNATImageStatus.CREATED,
                name="Trust1",
                reimport_count=0,
            ),
            ImagingProject(
                id=uuid4(),
                xnat_project_id=uuid4(),
                trust_id=trust_id_2,
                retrieve_image_status=XNATImageStatus.CREATED,
                name="Trust2",
                reimport_count=1,
            ),
        ]
        encoded_query = "ZXF1ZXJ5"

        mock_get_xnat_status.side_effect = [
            XnatProjectStatusInfo(retrieve_image_status=XNATImageStatus.CREATED, reimport_count=0),
            XnatProjectStatusInfo(
                retrieve_image_status=XNATImageStatus.RETRIEVE_COMPLETED, reimport_count=1
            ),
        ]

        # No existing pending tasks
        mock_db_session.exec.return_value.first.return_value = None

        results = get_imaging_project_statuses(imaging_projects_list, encoded_query, mock_db_session)

        assert len(results) == 2
        assert results[0].trust_id == trust_id_1
        assert results[0].project_creation_completed is True
        assert results[1].trust_id == trust_id_2
        assert results[1].project_creation_completed is False

        assert mock_get_xnat_status.call_count == 2
        # Should have added task records and committed
        assert mock_db_session.add.call_count == 2
        mock_db_session.commit.assert_called_once()


# --- update_xnat_user_profile ---
class TestUpdateXnatUserProfile:
    @patch(MOCK_GET_TRUSTS_PATH)
    @patch(MOCK_LOGGER_PATH)
    def test_queues_tasks_for_all_trusts(
        self,
        mock_logger: MagicMock,
        mock_get_trusts: MagicMock,
        mock_db_session: MagicMock,
    ):
        trust_list = [
            ITrust(id=uuid4(), name="Trust1"),
            ITrust(id=uuid4(), name="Trust2"),
        ]
        mock_get_trusts.return_value = trust_list

        request_data = IUpdateXnatProfile(email="user@example.com", enabled=True)

        update_xnat_user_profile(request_data, mock_db_session)

        assert mock_get_trusts.call_count == 1
        assert mock_db_session.add.call_count == 2
        mock_db_session.commit.assert_called_once()
        mock_logger.info.assert_called_once()


# --- reimport_failed_studies ---
class TestReimportFailedStudies:
    @patch(f"{MOCK_SERVICE_PATH}.base64_url_encode")
    @patch(MOCK_LOGGER_PATH)
    def test_reimport_logic(
        self,
        mock_logger: MagicMock,
        mock_b64_encode: MagicMock,
        mock_db_session: MagicMock,
    ):
        project_reimport_rate_minutes = 60  # 1 hour

        queries = [
            # This one should not run because last_reimport is within the rate limit
            IReimportQuery(
                query_id=uuid4(),
                query="SELECT * FROM studies",
                xnat_project_id=uuid4(),
                last_reimport=datetime.now(timezone.utc) - timedelta(minutes=30),
                trust_id=uuid4(),
                trust_name="T1",
            ),
            # This one should run because last_reimport is outside the rate limit
            IReimportQuery(
                query_id=uuid4(),
                query="SELECT * FROM studies_2",
                xnat_project_id=uuid4(),
                last_reimport=datetime.now(timezone.utc) - timedelta(minutes=90),
                trust_id=uuid4(),
                trust_name="T2",
            ),
            # No last reimport, so it should run
            IReimportQuery(
                query_id=uuid4(),
                query="SELECT * FROM studies_3",
                xnat_project_id=uuid4(),
                last_reimport=None,
                trust_id=uuid4(),
                trust_name="T3",
            ),
        ]

        mock_b64_encode.side_effect = lambda q: base64.urlsafe_b64encode(q.encode()).decode()

        # Mock DB returning XNATProjectStatus for eligible queries
        mock_xnat_status = MagicMock()
        mock_xnat_status.last_reimport = None
        mock_xnat_status.reimport_count = 0
        mock_db_session.exec.return_value.one_or_none.return_value = mock_xnat_status

        result = reimport_failed_studies(queries, mock_db_session, project_reimport_rate_minutes)

        assert result is True
        assert mock_b64_encode.call_count == 3
        # Two eligible queries should have been queued (Q2 and Q3)
        assert mock_db_session.add.call_count == 2
        mock_db_session.commit.assert_called_once()

    @patch(f"{MOCK_SERVICE_PATH}.base64_url_encode")
    @patch(MOCK_LOGGER_PATH)
    def test_reimport_record_not_found(
        self,
        mock_logger: MagicMock,
        mock_b64_encode: MagicMock,
        mock_db_session: MagicMock,
    ):
        """Should log error and continue when XNATProjectStatus record not found."""
        queries = [
            IReimportQuery(
                query_id=uuid4(),
                query="SELECT 1",
                xnat_project_id=uuid4(),
                last_reimport=None,
                trust_id=uuid4(),
                trust_name="T1",
            ),
        ]
        mock_b64_encode.side_effect = lambda q: "encoded"
        mock_db_session.exec.return_value.one_or_none.return_value = None

        result = reimport_failed_studies(queries, mock_db_session, 0)

        assert result is False
        mock_logger.error.assert_called()

    @patch(f"{MOCK_SERVICE_PATH}.base64_url_encode")
    @patch(MOCK_LOGGER_PATH)
    def test_reimport_exception_continues(
        self,
        mock_logger: MagicMock,
        mock_b64_encode: MagicMock,
        mock_db_session: MagicMock,
    ):
        """Should log error and continue when exception occurs during reimport."""
        queries = [
            IReimportQuery(
                query_id=uuid4(),
                query="SELECT 1",
                xnat_project_id=uuid4(),
                last_reimport=None,
                trust_id=uuid4(),
                trust_name="T1",
            ),
        ]
        mock_b64_encode.side_effect = lambda q: "encoded"
        mock_db_session.add.side_effect = Exception("DB error")

        result = reimport_failed_studies(queries, mock_db_session, 0)

        assert result is False
        mock_logger.error.assert_called()


class TestGetImagingProjectsEdgeCases:
    @patch(MOCK_LOGGER_PATH)
    def test_generic_exception(self, mock_logger: MagicMock, mock_db_session: MagicMock):
        """Should raise on non-SQLAlchemy exceptions."""
        mock_db_session.exec.side_effect = RuntimeError("Unexpected")
        with pytest.raises(RuntimeError, match="Unexpected"):
            get_imaging_projects(uuid4(), mock_db_session)

    @patch(MOCK_LOGGER_PATH)
    def test_sqlalchemy_error(self, mock_logger: MagicMock, mock_db_session: MagicMock):
        """Should raise on SQLAlchemy errors."""
        mock_db_session.exec.side_effect = SQLAlchemyError("DB error")
        with pytest.raises(SQLAlchemyError):
            get_imaging_projects(uuid4(), mock_db_session)


class TestGetXnatProjectStatusInfoEdgeCases:
    @patch(MOCK_LOGGER_PATH)
    def test_sqlalchemy_error(self, mock_logger: MagicMock, mock_db_session: MagicMock):
        """Should raise on SQLAlchemy errors."""
        mock_db_session.exec.side_effect = SQLAlchemyError("DB error")
        with pytest.raises(SQLAlchemyError):
            get_xnat_project_status_info(uuid4(), mock_db_session)


class TestUpdateXnatUserProfileEdgeCases:
    @patch(MOCK_GET_TRUSTS_PATH)
    @patch(MOCK_LOGGER_PATH)
    def test_no_trusts_found(
        self,
        mock_logger: MagicMock,
        mock_get_trusts: MagicMock,
        mock_db_session: MagicMock,
    ):
        """Should log error and return when no trusts found."""
        mock_get_trusts.return_value = []
        request_data = IUpdateXnatProfile(email="user@example.com", enabled=True)

        update_xnat_user_profile(request_data, mock_db_session)

        mock_logger.error.assert_called_once()
        mock_db_session.add.assert_not_called()


class TestGetImagingProjectStatusesEdgeCases:
    @patch(f"{MOCK_SERVICE_PATH}.get_xnat_project_status_info")
    @patch(MOCK_LOGGER_PATH)
    def test_empty_list(
        self,
        mock_logger: MagicMock,
        mock_get_xnat_status: MagicMock,
        mock_db_session: MagicMock,
    ):
        """Should log error when no imaging projects provided."""
        results = get_imaging_project_statuses([], "encoded", mock_db_session)

        assert results == []
        mock_logger.error.assert_called_once()
