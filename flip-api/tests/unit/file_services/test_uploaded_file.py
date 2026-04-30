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

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import status
from fastapi.exceptions import HTTPException
from fastapi.testclient import TestClient

from flip_api.auth.dependencies import verify_token
from flip_api.config import Settings
from flip_api.db.database import get_session
from flip_api.db.models.main_models import UploadedFiles
from flip_api.domain.schemas.file import BucketStatus, FileUploadStatus, ScannedFileInput
from flip_api.file_services.uploaded_file import process_scanned_file
from flip_api.main import app

# ---------- Authorisation tests for /files/process-scanned-file ----------

client = TestClient(app)

auth_test_user_id = uuid.uuid4()
auth_test_model_id = uuid.uuid4()
auth_test_file_name = "weights.bin"


@pytest.fixture
def override_auth_dependencies():
    """Inject a deterministic user_id and a mock DB session into the endpoint."""
    mock_session = MagicMock()
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[verify_token] = lambda: auth_test_user_id
    yield mock_session
    app.dependency_overrides.clear()


@pytest.fixture
def mocked_settings_for_auth():
    settings = Settings(UPLOADED_MODEL_FILES_BUCKET="test-uploaded-bucket")
    with patch("flip_api.file_services.uploaded_file.get_settings", return_value=settings):
        yield settings


@pytest.fixture
def mock_s3_for_auth():
    with patch("flip_api.file_services.uploaded_file.S3Client") as mock_client:
        instance = MagicMock()
        instance.head_object.return_value = {"ContentLength": 1024, "ContentType": "application/octet-stream"}
        mock_client.return_value = instance
        yield instance


def test_process_scanned_file_returns_403_when_user_cannot_modify_model(
    override_auth_dependencies, mocked_settings_for_auth, mock_s3_for_auth
):
    mock_session = override_auth_dependencies
    with patch("flip_api.file_services.uploaded_file.can_modify_model", return_value=False):
        response = client.post(f"/api/files/process-scanned-file/{auth_test_model_id}/{auth_test_file_name}")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert str(auth_test_user_id) in response.json()["detail"]
    mock_session.add.assert_not_called()
    mock_session.commit.assert_not_called()
    mock_s3_for_auth.head_object.assert_not_called()


def test_process_scanned_file_succeeds_when_user_can_modify_model(
    override_auth_dependencies, mocked_settings_for_auth, mock_s3_for_auth
):
    mock_session = override_auth_dependencies
    mock_session.exec.return_value.first.return_value = None  # no existing row → insert path
    with patch("flip_api.file_services.uploaded_file.can_modify_model", return_value=True):
        response = client.post(f"/api/files/process-scanned-file/{auth_test_model_id}/{auth_test_file_name}")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"message": "File processed successfully"}
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()


def test_process_scanned_file_returns_422_for_non_uuid_model_id(
    override_auth_dependencies, mocked_settings_for_auth, mock_s3_for_auth
):
    """FastAPI must reject malformed model_id at the path-parameter layer."""
    with patch("flip_api.file_services.uploaded_file.can_modify_model", return_value=True) as can_modify:
        response = client.post(f"/api/files/process-scanned-file/not-a-uuid/{auth_test_file_name}")

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    can_modify.assert_not_called()


# ---------- Legacy SNS-pipeline tests (skipped, see comment below) ----------


@pytest.fixture
def mock_s3_client():
    """Mock S3Client for testing."""
    with patch("flip_api.file_services.uploaded_file.S3Client") as mock_client:
        s3_instance = MagicMock()
        mock_client.return_value = s3_instance
        # Mock head_object to return file metadata
        s3_instance.head_object.return_value = {"ContentLength": 1024, "ContentType": "text/plain"}
        yield s3_instance


@pytest.fixture
def mocked_settings():
    mock = Settings(
        SCANNED_MODEL_FILES_BUCKET="test-secure-bucket",
    )
    with patch("flip_api.file_services.uploaded_file.get_settings", return_value=mock):
        yield mock


@pytest.fixture
def clean_file_event():
    """Create a sample SNS event for a clean file."""
    model_id = str(uuid.uuid4())
    file_name = "test.txt"
    key = f"{model_id}/{file_name}"

    message = {"bucket": "test-bucket", "key": key, "status": BucketStatus.CLEAN.value}

    return ScannedFileInput(Records=[{"Sns": {"Message": json.dumps(message)}}])


@pytest.fixture
def infected_file_event():
    """Create a sample SNS event for an infected file."""
    model_id = str(uuid.uuid4())
    file_name = "infected.txt"
    key = f"{model_id}/{file_name}"

    message = {"bucket": "test-bucket", "key": key, "status": BucketStatus.INFECTED.value}

    return ScannedFileInput(Records=[{"Sns": {"Message": json.dumps(message)}}])


@pytest.mark.skip("Bypassing virus scanning and AWS SNS after model file upload for the demo.")
def test_process_clean_file_success(mock_s3_client, mocked_settings, clean_file_event):
    """Test successful processing of a clean file."""
    # Mock the database session
    mock_db = MagicMock()
    mock_db.exec.return_value.first.return_value = None  # File doesn't exist in DB yet

    # Call the function
    result = process_scanned_file(clean_file_event, mock_db)

    # Verify result is the original message
    message = json.loads(clean_file_event.Records[0]["Sns"]["Message"])
    assert result == message

    # Verify database operations
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()

    # Verify S3 operations
    key = message["key"]
    mock_s3_client.head_object.assert_called()
    mock_s3_client.copy_object.assert_called_once_with(message["bucket"], key, "test-secure-bucket", key)
    mock_s3_client.delete_object.assert_called_once_with(message["bucket"], key)


@pytest.mark.skip("Bypassing virus scanning and AWS SNS after model file upload for the demo.")
def test_process_existing_file_update(mock_s3_client, mocked_settings, clean_file_event):
    """Test updating an existing file in the database."""
    # Create existing file record
    message = json.loads(clean_file_event.Records[0]["Sns"]["Message"])
    key_parts = message["key"].split("/")
    model_id = key_parts[0]
    file_name = key_parts[1]

    existing_file = UploadedFiles(
        name=file_name, status=FileUploadStatus.SCANNING, size=0, type="unknown", model_id=model_id
    )

    # Mock the database session
    mock_db = MagicMock()
    mock_db.exec.return_value.first.return_value = existing_file

    # Call the function
    process_scanned_file(clean_file_event, mock_db)

    # Verify file was updated not added
    mock_db.add.assert_not_called()
    mock_db.commit.assert_called_once()

    # Verify file attributes were updated
    assert existing_file.status == FileUploadStatus.COMPLETED
    assert existing_file.size == 1024
    assert existing_file.type == "text/plain"


@pytest.mark.skip("Bypassing virus scanning and AWS SNS after model file upload for the demo.")
def test_process_infected_file(mock_s3_client, mocked_settings, infected_file_event):
    """Test handling of an infected file."""
    # Mock the database session
    mock_db = MagicMock()
    mock_db.exec.return_value.first.return_value = None

    # Call the function and expect an HTTPException
    with pytest.raises(HTTPException) as excinfo:
        process_scanned_file(infected_file_event, mock_db)

    # Verify the status code is 400 (Bad Request)
    assert excinfo.value.status_code == 400

    # Verify S3 delete was called to remove the infected file
    message = json.loads(infected_file_event.Records[0]["Sns"]["Message"])
    mock_s3_client.delete_object.assert_called_once_with(message["bucket"], message["key"])

    # Verify file wasn't copied
    mock_s3_client.copy_object.assert_not_called()


@pytest.mark.skip("Bypassing virus scanning and AWS SNS after model file upload for the demo.")
def test_s3_head_object_exception(mock_s3_client, mocked_settings, clean_file_event):
    """Test handling an exception when retrieving file metadata."""
    # Setup mock to raise an exception
    mock_s3_client.head_object.side_effect = Exception("S3 head_object error")

    # Mock the database session
    mock_db = MagicMock()

    # Call the function and expect an HTTPException
    with pytest.raises(HTTPException) as excinfo:
        process_scanned_file(clean_file_event, mock_db)

    # Verify the status code is 500 (Internal Server Error)
    assert excinfo.value.status_code == 500
    assert "Unable to retrieve the file's details" in str(excinfo.value.detail)


@pytest.mark.skip("Bypassing virus scanning and AWS SNS after model file upload for the demo.")
def test_s3_copy_exception(mock_s3_client, mocked_settings, clean_file_event):
    """Test handling an exception when copying file to secure bucket."""
    # Setup mock to raise an exception on copy_object
    mock_s3_client.copy_object.side_effect = Exception("S3 copy error")

    # Mock the database session
    mock_db = MagicMock()
    mock_db.exec.return_value.first.return_value = None

    # Call the function and expect an HTTPException
    with pytest.raises(HTTPException) as excinfo:
        process_scanned_file(clean_file_event, mock_db)

    # Verify the status code is 500 (Internal Server Error)
    assert excinfo.value.status_code == 500
    assert "Unable to copy scanned file in secure bucket" in str(excinfo.value.detail)


@pytest.mark.skip("Bypassing virus scanning and AWS SNS after model file upload for the demo.")
def test_invalid_model_id(mock_s3_client, mocked_settings):
    """Test handling an invalid model ID in the file key."""
    # Create event with empty model ID
    message = {
        "bucket": "test-bucket",
        "key": "/test.txt",  # Missing model ID
        "status": BucketStatus.CLEAN.value,
    }

    event = ScannedFileInput(Records=[{"Sns": {"Message": json.dumps(message)}}])

    # Mock the database session
    mock_db = MagicMock()

    # Call the function and expect an HTTPException
    with pytest.raises(HTTPException) as excinfo:
        process_scanned_file(event, mock_db)

    # Verify the status code is 400 (Bad Request)
    assert excinfo.value.status_code == 400
    assert "valid model ID" in str(excinfo.value.detail)


@pytest.mark.skip("Bypassing virus scanning and AWS SNS after model file upload for the demo.")
def test_s3_verify_exception(mock_s3_client, mocked_settings, clean_file_event):
    """Test handling an exception when verifying file in secure bucket."""
    # Setup mock to raise an exception on second head_object call
    mock_s3_client.head_object.side_effect = [
        {"ContentLength": 1024, "ContentType": "text/plain"},  # First call succeeds
        Exception("S3 verification error"),  # Second call fails
    ]

    # Mock the database session
    mock_db = MagicMock()
    mock_db.exec.return_value.first.return_value = None

    # Call the function and expect an HTTPException
    with pytest.raises(HTTPException) as excinfo:
        process_scanned_file(clean_file_event, mock_db)

    # Verify the status code is 500 (Internal Server Error)
    assert excinfo.value.status_code == 500
    assert "Unable to access scanned file in secure bucket" in str(excinfo.value.detail)
