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
