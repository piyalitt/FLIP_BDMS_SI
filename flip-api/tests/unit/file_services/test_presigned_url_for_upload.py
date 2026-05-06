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

"""Unit tests for ``flip_api.file_services.presigned_url_for_upload``.

Pins the logging contract for both branches of the upload route: the
production path that calls ``S3Client.get_put_presigned_url`` and the
``PRE_SIGNED_URL`` env-override path that historically logged the
override value verbatim. Neither may write a signed URL to a log line.
"""

import logging
import re
import uuid
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from flip_api.auth.dependencies import verify_token
from flip_api.config import Settings
from flip_api.db.database import get_session
from flip_api.main import app

_FAKE_SIGNED_URL = (
    "https://test-bucket.s3.amazonaws.com/model-id/weights.bin?"
    "X-Amz-Algorithm=AWS4-HMAC-SHA256&"
    "X-Amz-Credential=AKIAEXAMPLEKEY%2F20260506%2Feu-west-2%2Fs3%2Faws4_request&"
    "X-Amz-Date=20260506T000000Z&"
    "X-Amz-Expires=600&"
    "X-Amz-SignedHeaders=host&"
    "X-Amz-Signature=deadbeefcafe1234567890abcdef"
)
_S3_URL_WITH_QUERY = re.compile(r"https?://[^\s]*s3[^\s/]*\.amazonaws\.com[^\s]*\?[^\s]*", re.IGNORECASE)
_FORBIDDEN_TOKENS = ("X-Amz-Signature=", "X-Amz-Credential=", "X-Amz-SignedHeaders=")


def _assert_logs_have_no_presigned_url(records: list[logging.LogRecord]) -> None:
    for record in records:
        candidates = [record.getMessage()]
        if record.args:
            candidates.append(repr(record.args))
        for candidate in candidates:
            for token in _FORBIDDEN_TOKENS:
                assert token not in candidate, (
                    f"Pre-signed URL artefact {token!r} leaked into a log line: {candidate!r}"
                )
            assert not _S3_URL_WITH_QUERY.search(candidate), (
                f"Pre-signed S3 URL leaked into a log line: {candidate!r}"
            )


@pytest.fixture
def upload_route_settings():
    """Settings stub the upload route reads via ``get_settings``."""
    settings = Settings(UPLOADED_MODEL_FILES_BUCKET="test-uploaded-bucket")
    with patch("flip_api.file_services.presigned_url_for_upload.get_settings", return_value=settings):
        yield settings


@pytest.fixture
def override_upload_dependencies():
    """Inject a deterministic user_id and a mock DB session into the endpoint."""
    user_id = uuid4()
    mock_session = MagicMock()
    # The endpoint runs ``existing_model = result.first()`` after the DB query;
    # returning anything truthy avoids the 404 branch.
    mock_session.exec.return_value.first.return_value = MagicMock()
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[verify_token] = lambda: user_id
    yield user_id
    app.dependency_overrides.clear()


def test_presigned_url_endpoint_success_path_does_not_log_url(
    caplog, upload_route_settings, override_upload_dependencies
):
    """End-to-end: hitting the route with a valid model returns the URL but never logs it."""
    caplog.set_level(logging.DEBUG, logger="uvicorn")
    model_id = uuid.uuid4()

    with (
        patch("flip_api.file_services.presigned_url_for_upload.can_modify_model", return_value=True),
        patch("flip_api.file_services.presigned_url_for_upload.S3Client") as mock_s3_cls,
    ):
        mock_s3 = MagicMock()
        mock_s3.get_put_presigned_url.return_value = _FAKE_SIGNED_URL
        mock_s3_cls.return_value = mock_s3

        response = TestClient(app).post(
            f"/api/files/preSignedUrl/model/{model_id}",
            json={"fileName": "weights.bin"},
        )

    assert response.status_code == 200, response.text
    assert response.json() == _FAKE_SIGNED_URL
    _assert_logs_have_no_presigned_url(caplog.records)


def test_presigned_url_endpoint_env_override_path_does_not_log_url(
    caplog, override_upload_dependencies
):
    """The PRE_SIGNED_URL env-override path historically logged the override.

    A developer pasting a real signed URL into PRE_SIGNED_URL for local
    testing would have had it written straight to the application log
    before this fix; pin that it can no longer happen.
    """
    caplog.set_level(logging.DEBUG, logger="uvicorn")
    model_id = uuid.uuid4()

    settings = Settings(
        UPLOADED_MODEL_FILES_BUCKET="test-uploaded-bucket",
        PRE_SIGNED_URL=_FAKE_SIGNED_URL,
    )
    with (
        patch("flip_api.file_services.presigned_url_for_upload.get_settings", return_value=settings),
        patch("flip_api.file_services.presigned_url_for_upload.can_modify_model", return_value=True),
    ):
        response = TestClient(app).post(
            f"/api/files/preSignedUrl/model/{model_id}",
            json={"fileName": "weights.bin"},
        )

    assert response.status_code == 200, response.text
    assert response.json() == _FAKE_SIGNED_URL
    _assert_logs_have_no_presigned_url(caplog.records)


def test_presigned_url_endpoint_rejects_path_traversal_filename(
    upload_route_settings, override_upload_dependencies
):
    """The ``fileName`` validator must short-circuit before any S3 call."""
    model_id = uuid.uuid4()

    with (
        patch("flip_api.file_services.presigned_url_for_upload.can_modify_model", return_value=True),
        patch("flip_api.file_services.presigned_url_for_upload.S3Client") as mock_s3_cls,
    ):
        response = TestClient(app).post(
            f"/api/files/preSignedUrl/model/{model_id}",
            json={"fileName": "../escape.bin"},
        )

    assert response.status_code == 422, response.text
    mock_s3_cls.assert_not_called()
