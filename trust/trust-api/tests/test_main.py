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
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from log_config import LoggingMiddleware

from trust_api.main import app
from trust_api.routers.schemas import CentralHubProject, CentralHubUser, CohortQueryInput


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# App metadata
# ---------------------------------------------------------------------------
def test_app_metadata():
    assert app.title == "Trust API"
    assert app.version == "0.1.0"
    assert app.docs_url == "/docs"
    assert app.redoc_url == "/redoc"


# ---------------------------------------------------------------------------
# Middleware registration
# ---------------------------------------------------------------------------
def test_logging_middleware_registered():
    middleware_classes = [m.cls for m in app.user_middleware]
    assert LoggingMiddleware in middleware_classes


# ---------------------------------------------------------------------------
# Health router mounted on the real app
# ---------------------------------------------------------------------------
def test_health_endpoint(client):
    response = client.get("/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Cohort router mounted on the real app
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("trust_api.routers.cohort.make_request", new_callable=AsyncMock)
async def test_cohort_router_mounted(mock_make_request, client):
    mock_make_request.return_value = {"status": "ok"}
    query_input = CohortQueryInput(
        encrypted_project_id="test-project-id",
        query_id="test-query-id",
        query_name="Test Query",
        query="SELECT * FROM cohort",
        trust_id="test-trust-id",
    )
    response = client.post("/cohort", json=query_input.model_dump())
    assert response.status_code != 404


# ---------------------------------------------------------------------------
# Imaging router mounted on the real app
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("trust_api.routers.imaging.make_request", new_callable=AsyncMock)
async def test_imaging_router_mounted(mock_make_request, client):
    mock_make_request.return_value = {"status": "ok"}
    project = CentralHubProject(
        project_id=uuid4(),
        trust_id=uuid4(),
        project_name="Test Project",
        query="SELECT * FROM studies",
        users=[CentralHubUser(id=uuid4(), email="user@example.com", is_disabled=False)],
    )
    payload = json.loads(project.model_dump_json())
    response = client.post("/imaging/", json=payload)
    assert response.status_code != 404
