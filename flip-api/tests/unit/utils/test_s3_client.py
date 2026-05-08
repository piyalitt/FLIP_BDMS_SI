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

"""Unit tests for ``flip_api.utils.s3_client``.

Pins the logging contract: the bare ``S3Client.get_put_presigned_url``
call must never write the URL to a log line, and the TTL it requests
from boto3 must satisfy the 600 s ceiling. Together with the tests in
``tests/unit/file_services/test_presigned_url_for_upload.py`` and
``tests/unit/file_services/test_retrieve_federated_results.py``, this
module forms the policy retest required by the FLIP-PT review brief:
no log line may contain ``X-Amz-Signature=``, ``X-Amz-Credential=``,
or any ``s3.amazonaws.com/...?...`` URL.
"""

import logging
import re
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from flip_api.utils.s3_client import MAX_PUT_PRESIGNED_URL_TTL_SECONDS, S3Client

# Mirrors the shape of a real SigV4 pre-signed URL so the assertions
# exercise the same query-string layout AWS would emit in production.
_FAKE_SIGNED_URL = (
    "https://test-bucket.s3.amazonaws.com/model-id/weights.bin?"
    "X-Amz-Algorithm=AWS4-HMAC-SHA256&"
    "X-Amz-Credential=AKIAEXAMPLEKEY%2F20260506%2Feu-west-2%2Fs3%2Faws4_request&"
    "X-Amz-Date=20260506T000000Z&"
    "X-Amz-Expires=600&"
    "X-Amz-SignedHeaders=host&"
    "X-Amz-Signature=deadbeefcafe1234567890abcdef"
)
# Match any URL that carries SigV4 query parameters, regardless of host —
# AWS, moto/localstack (``http://localhost:4566/...``), GovCloud, S3
# Accelerate, and path-style endpoints all produce ``...?X-Amz-...`` URLs.
_S3_URL_WITH_QUERY = re.compile(r"https?://\S+\?\S*X-Amz-", re.IGNORECASE)
_FORBIDDEN_TOKENS = (
    "X-Amz-Signature=",
    "X-Amz-Credential=",
    "X-Amz-SignedHeaders=",
    "X-Amz-Security-Token=",
    "Authorization=AWS4-HMAC-SHA256",
)


def _assert_logs_have_no_presigned_url(records: list[logging.LogRecord]) -> None:
    for record in records:
        candidates = [record.getMessage()]
        if record.args:
            candidates.append(repr(record.args))
        # Inspect the attached exception too: ``logger.exception(...)`` (or any
        # ``logger.error(..., exc_info=True)``) populates ``exc_info``, and the
        # default formatter emits ``str(exc_value)`` plus the traceback into the
        # final log line. Pinning the policy here means a future regression
        # that re-adds ``exc_info`` cannot let URL material slip through that
        # channel without tripping a test.
        if record.exc_info:
            _, exc_value, _ = record.exc_info
            candidates.append(repr(exc_value))
            candidates.append(str(exc_value))
        if record.exc_text:
            candidates.append(record.exc_text)
        for candidate in candidates:
            for token in _FORBIDDEN_TOKENS:
                assert token not in candidate, (
                    f"Pre-signed URL artefact {token!r} leaked into a log line: {candidate!r}"
                )
            assert not _S3_URL_WITH_QUERY.search(candidate), (
                f"Pre-signed S3 URL leaked into a log line: {candidate!r}"
            )


def test_get_put_presigned_url_does_not_log_url(caplog):
    """``S3Client.get_put_presigned_url`` must not print the URL it returns."""
    caplog.set_level(logging.DEBUG, logger="uvicorn")

    with patch("flip_api.utils.s3_client.boto3.client") as mock_boto:
        boto = MagicMock()
        boto.generate_presigned_url.return_value = _FAKE_SIGNED_URL
        mock_boto.return_value = boto

        url = S3Client().get_put_presigned_url("s3://test-bucket/model-id/weights.bin")

    assert url == _FAKE_SIGNED_URL
    _assert_logs_have_no_presigned_url(caplog.records)


def test_get_put_presigned_url_caps_ttl_at_security_ceiling():
    """A caller passing a permissive TTL must still get the security ceiling."""
    with patch("flip_api.utils.s3_client.boto3.client") as mock_boto:
        boto = MagicMock()
        boto.generate_presigned_url.return_value = _FAKE_SIGNED_URL
        mock_boto.return_value = boto

        S3Client().get_put_presigned_url("s3://test-bucket/key", expiration=3600)

    _, kwargs = boto.generate_presigned_url.call_args
    assert kwargs["ExpiresIn"] == MAX_PUT_PRESIGNED_URL_TTL_SECONDS
    assert kwargs["ExpiresIn"] <= 600


def test_get_put_presigned_url_default_ttl_is_at_most_600s():
    """Default TTL must satisfy the 'TTL <= 600 s' policy requirement."""
    with patch("flip_api.utils.s3_client.boto3.client") as mock_boto:
        boto = MagicMock()
        boto.generate_presigned_url.return_value = _FAKE_SIGNED_URL
        mock_boto.return_value = boto

        S3Client().get_put_presigned_url("s3://test-bucket/key")

    _, kwargs = boto.generate_presigned_url.call_args
    assert kwargs["ExpiresIn"] <= 600


def test_get_put_presigned_url_logs_warning_when_clamped(caplog):
    """Over-ceiling callers must leave a warning trail so the silent clamp is auditable."""
    caplog.set_level(logging.WARNING, logger="uvicorn")

    with patch("flip_api.utils.s3_client.boto3.client") as mock_boto:
        boto = MagicMock()
        boto.generate_presigned_url.return_value = _FAKE_SIGNED_URL
        mock_boto.return_value = boto

        S3Client().get_put_presigned_url("s3://test-bucket/key", expiration=3600)

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("3600" in r.getMessage() and "600" in r.getMessage() for r in warnings), (
        f"Expected a clamp warning citing both 3600s and 600s; got: {[r.getMessage() for r in warnings]}"
    )


def test_get_put_presigned_url_does_not_warn_at_or_below_ceiling(caplog):
    """A within-policy caller must not trip the warning."""
    caplog.set_level(logging.WARNING, logger="uvicorn")

    with patch("flip_api.utils.s3_client.boto3.client") as mock_boto:
        boto = MagicMock()
        boto.generate_presigned_url.return_value = _FAKE_SIGNED_URL
        mock_boto.return_value = boto

        S3Client().get_put_presigned_url("s3://test-bucket/key", expiration=300)

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert not warnings, f"Did not expect a warning for in-policy TTL: {[r.getMessage() for r in warnings]}"


def test_get_put_presigned_url_at_ceiling_passes_through():
    """Boundary case: an ``expiration`` exactly at the ceiling must round-trip unchanged."""
    with patch("flip_api.utils.s3_client.boto3.client") as mock_boto:
        boto = MagicMock()
        boto.generate_presigned_url.return_value = _FAKE_SIGNED_URL
        mock_boto.return_value = boto

        S3Client().get_put_presigned_url(
            "s3://test-bucket/key", expiration=MAX_PUT_PRESIGNED_URL_TTL_SECONDS
        )

    _, kwargs = boto.generate_presigned_url.call_args
    assert kwargs["ExpiresIn"] == MAX_PUT_PRESIGNED_URL_TTL_SECONDS


def test_max_put_presigned_url_ttl_is_600s():
    """Pin the ceiling value itself — moving it requires a security review."""
    assert MAX_PUT_PRESIGNED_URL_TTL_SECONDS == 600


def test_get_put_presigned_url_does_not_log_url_on_client_error(caplog):
    """If boto raises ``ClientError``, the error log line must not contain the URL.

    ``ClientError`` from ``generate_presigned_url`` does not carry the URL today,
    but pin the contract so a future boto3 change cannot regress the redaction.
    """
    caplog.set_level(logging.DEBUG, logger="uvicorn")

    with patch("flip_api.utils.s3_client.boto3.client") as mock_boto:
        boto = MagicMock()
        # Simulate the worst case: an exception whose __str__ contains the URL.
        boto.generate_presigned_url.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": _FAKE_SIGNED_URL}}, "generate_presigned_url"
        )
        mock_boto.return_value = boto

        with pytest.raises(Exception, match="Unable to create a pre-signed URL"):
            S3Client().get_put_presigned_url("s3://test-bucket/key")

    # The wrapped exception we re-raise has a static message, but the helper
    # also inspects the attached ``exc_info`` — if ``logger.exception`` were
    # ever reintroduced here, the boto ``ClientError`` (whose ``str()``
    # contains ``_FAKE_SIGNED_URL``) would land in the formatted traceback
    # and trip this assertion.
    _assert_logs_have_no_presigned_url(caplog.records)
