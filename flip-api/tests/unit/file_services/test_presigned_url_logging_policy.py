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

"""Retest: pre-signed URLs must never reach application logs.

This module pins the logging contract for every code path that can
produce a pre-signed URL — the ``S3Client`` helpers, the ``preSignedUrl``
upload route (success path and ``PRE_SIGNED_URL`` env-override path),
and the ``fl/results`` retrieval route. It also pins the schema-level
filename sanitisation that prevents ``body.fileName`` from steering the
S3 key off-prefix.

Required by the policy: no log line may contain ``X-Amz-Signature=``,
``X-Amz-Credential=``, or any ``s3.amazonaws.com/...?...`` URL.
"""

import logging
import re
import uuid
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from flip_api.auth.dependencies import verify_token
from flip_api.config import Settings
from flip_api.db.database import get_session
from flip_api.domain.schemas.file import UploadFileBody
from flip_api.main import app
from flip_api.utils.s3_client import MAX_PUT_PRESIGNED_URL_TTL_SECONDS, S3Client

# A query string that mirrors a real SigV4 pre-signed URL. The mock S3
# client returns this so the assertions exercise the same shape that AWS
# would emit in production.
_FAKE_SIGNED_URL = (
    "https://test-bucket.s3.amazonaws.com/model-id/weights.bin?"
    "X-Amz-Algorithm=AWS4-HMAC-SHA256&"
    "X-Amz-Credential=AKIAEXAMPLEKEY%2F20260506%2Feu-west-2%2Fs3%2Faws4_request&"
    "X-Amz-Date=20260506T000000Z&"
    "X-Amz-Expires=600&"
    "X-Amz-SignedHeaders=host&"
    "X-Amz-Signature=deadbeefcafe1234567890abcdef"
)

# Pattern from the policy: any S3 URL with a query string.
# ``re.IGNORECASE`` because S3 endpoints can vary in casing
# (region-specific, virtual-hosted-style, path-style, etc.).
_S3_URL_WITH_QUERY = re.compile(r"https?://[^\s]*s3[^\s/]*\.amazonaws\.com[^\s]*\?[^\s]*", re.IGNORECASE)
_FORBIDDEN_TOKENS = ("X-Amz-Signature=", "X-Amz-Credential=", "X-Amz-SignedHeaders=")


def _assert_logs_have_no_presigned_url(records: list[logging.LogRecord]) -> None:
    """Assert no log record carries any signed-URL artefact."""
    for record in records:
        # ``getMessage`` resolves %s substitutions; ``args`` covers logging
        # calls that pass values as arguments (rare in this codebase but
        # cheap to defend against).
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


# ---------------------------------------------------------------------------
# S3Client.get_put_presigned_url — the lowest-level producer
# ---------------------------------------------------------------------------


def test_s3_client_get_put_presigned_url_does_not_log_url(caplog):
    """``S3Client.get_put_presigned_url`` must not print the URL it returns."""
    caplog.set_level(logging.DEBUG, logger="uvicorn")

    with patch("flip_api.utils.s3_client.boto3.client") as mock_boto:
        boto = MagicMock()
        boto.generate_presigned_url.return_value = _FAKE_SIGNED_URL
        mock_boto.return_value = boto

        url = S3Client().get_put_presigned_url("s3://test-bucket/model-id/weights.bin")

    assert url == _FAKE_SIGNED_URL
    _assert_logs_have_no_presigned_url(caplog.records)


def test_s3_client_get_put_presigned_url_caps_ttl_at_security_ceiling():
    """A caller passing a permissive TTL must still get the security ceiling."""
    with patch("flip_api.utils.s3_client.boto3.client") as mock_boto:
        boto = MagicMock()
        boto.generate_presigned_url.return_value = _FAKE_SIGNED_URL
        mock_boto.return_value = boto

        S3Client().get_put_presigned_url("s3://test-bucket/key", expiration=3600)

    _, kwargs = boto.generate_presigned_url.call_args
    assert kwargs["ExpiresIn"] == MAX_PUT_PRESIGNED_URL_TTL_SECONDS
    assert kwargs["ExpiresIn"] <= 600


def test_s3_client_get_put_presigned_url_default_ttl_is_at_most_600s():
    """Default TTL must satisfy the 'TTL ≤ 600 s' policy requirement."""
    with patch("flip_api.utils.s3_client.boto3.client") as mock_boto:
        boto = MagicMock()
        boto.generate_presigned_url.return_value = _FAKE_SIGNED_URL
        mock_boto.return_value = boto

        S3Client().get_put_presigned_url("s3://test-bucket/key")

    _, kwargs = boto.generate_presigned_url.call_args
    assert kwargs["ExpiresIn"] <= 600


# ---------------------------------------------------------------------------
# /files/preSignedUrl/model/{model_id} — the production code path
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# /files/model/{model_id}/fl/results — the federated-results retrieval route
# ---------------------------------------------------------------------------


def test_retrieve_federated_results_does_not_log_url_list(caplog):
    """The route used to JSON-dump the entire list of presigned URLs at INFO."""
    caplog.set_level(logging.DEBUG, logger="uvicorn")
    model_id = uuid.uuid4()
    user_id = uuid.uuid4()

    settings = Settings(
        UPLOADED_FEDERATED_DATA_BUCKET="s3://test-bucket/uploaded_federated_data",
    )

    mock_session = MagicMock()
    # ``model_exists`` truthy bypasses the 404 path.
    mock_session.exec.return_value.first.return_value = MagicMock()
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[verify_token] = lambda: user_id
    try:
        with (
            patch("flip_api.file_services.retrieve_federated_results.get_settings", return_value=settings),
            patch("flip_api.file_services.retrieve_federated_results.can_access_model", return_value=True),
            patch("flip_api.file_services.retrieve_federated_results.S3Client") as mock_s3_cls,
        ):
            mock_s3 = MagicMock()
            mock_s3.list_objects.return_value = [
                f"s3://test-bucket/uploaded_federated_data/{model_id}/metrics.json",
                f"s3://test-bucket/uploaded_federated_data/{model_id}/weights.bin",
            ]
            mock_s3.get_presigned_url.side_effect = [
                _FAKE_SIGNED_URL,
                _FAKE_SIGNED_URL.replace("weights.bin", "metrics.json"),
            ]
            mock_s3_cls.return_value = mock_s3

            response = TestClient(app).get(f"/api/files/model/{model_id}/fl/results")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    assert len(response.json()) == 2
    _assert_logs_have_no_presigned_url(caplog.records)


# ---------------------------------------------------------------------------
# UploadFileBody schema — server-side filename sanitisation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_name",
    [
        "../escape.bin",
        "..",
        ".",
        "subdir/file.bin",
        "subdir\\file.bin",
        "file\x00.bin",
        "file\x07.bin",
        "  leading-space.bin",
        "trailing-space.bin  ",
        "",
    ],
)
def test_upload_file_body_rejects_unsafe_file_names(bad_name):
    """``body.fileName`` is concatenated into the S3 key — reject anything dangerous."""
    with pytest.raises(ValidationError):
        UploadFileBody(fileName=bad_name)


@pytest.mark.parametrize(
    "good_name",
    [
        "weights.bin",
        "model.tar.gz",
        "MyModel-v2.pth",
        "report (final).pdf",
        "spaces in name.bin",
    ],
)
def test_upload_file_body_accepts_safe_file_names(good_name):
    """Sanity check: ordinary filenames must still pass."""
    body = UploadFileBody(fileName=good_name)
    assert body.fileName == good_name


def test_upload_file_body_max_length_caps_at_255():
    """Reject pathologically long names that could bloat the S3 key."""
    with pytest.raises(ValidationError):
        UploadFileBody(fileName="a" * 256)
