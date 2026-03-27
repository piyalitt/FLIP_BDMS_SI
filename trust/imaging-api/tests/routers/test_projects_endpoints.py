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

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from imaging_api.main import app
from imaging_api.routers.schemas import Experiment, Project, Subject
from imaging_api.utils.auth import get_xnat_auth_headers
from imaging_api.utils.exceptions import AlreadyExistsError, NotFoundError

client = TestClient(app)


@pytest.fixture(autouse=True)
def override_auth_headers():
    app.dependency_overrides[get_xnat_auth_headers] = lambda: {"Cookie": "JSESSIONID=fake"}
    yield
    app.dependency_overrides.clear()


_SAMPLE_PROJECT = Project(
    pi_firstname="John",
    secondary_ID="hub-123",
    pi_lastname="Doe",
    name="Test Project",
    description="A test project",
    ID="PROJ1",
    URI="/data/projects/PROJ1",
)


# ── GET /projects/ ──


def test_get_projects_success():
    with patch("imaging_api.routers.projects.get_all_projects", return_value=[_SAMPLE_PROJECT]):
        response = client.get("/projects/")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["ID"] == "PROJ1"


def test_get_projects_error():
    with patch("imaging_api.routers.projects.get_all_projects", side_effect=Exception("connection error")):
        response = client.get("/projects/")

    assert response.status_code == 500


# ── POST /projects/ ──


def test_create_project_success():
    with patch("imaging_api.routers.projects.create_project", return_value=_SAMPLE_PROJECT):
        response = client.post(
            "/projects/",
            params={
                "project_id": "PROJ1",
                "project_secondary_id": "hub-123",
                "project_name": "Test Project",
            },
        )

    assert response.status_code == 200
    assert response.json()["ID"] == "PROJ1"


def test_create_project_already_exists():
    with patch(
        "imaging_api.routers.projects.create_project",
        side_effect=AlreadyExistsError("Project already exists"),
    ):
        response = client.post(
            "/projects/",
            params={
                "project_id": "PROJ1",
                "project_secondary_id": "hub-123",
                "project_name": "Test Project",
            },
        )

    assert response.status_code == 400


def test_create_project_error():
    with patch("imaging_api.routers.projects.create_project", side_effect=Exception("XNAT error")):
        response = client.post(
            "/projects/",
            params={
                "project_id": "PROJ1",
                "project_secondary_id": "hub-123",
                "project_name": "Test Project",
            },
        )

    assert response.status_code == 500


# ── DELETE /projects/{project_id} ──


def test_delete_project_success():
    with patch(
        "imaging_api.routers.projects.delete_project",
        new_callable=AsyncMock,
        return_value=_SAMPLE_PROJECT,
    ):
        response = client.delete("/projects/PROJ1")

    assert response.status_code == 200


def test_delete_project_not_found():
    with patch(
        "imaging_api.routers.projects.delete_project",
        new_callable=AsyncMock,
        side_effect=NotFoundError("Project not found"),
    ):
        response = client.delete("/projects/BAD_PROJ")

    assert response.status_code == 404


def test_delete_project_error():
    with patch(
        "imaging_api.routers.projects.delete_project",
        new_callable=AsyncMock,
        side_effect=Exception("XNAT error"),
    ):
        response = client.delete("/projects/PROJ1")

    assert response.status_code == 500


# ── GET /projects/{project_id} ──


def test_get_project_success():
    with patch("imaging_api.routers.projects.get_project", return_value=_SAMPLE_PROJECT):
        response = client.get("/projects/PROJ1")

    assert response.status_code == 200
    assert response.json()["ID"] == "PROJ1"


def test_get_project_not_found():
    with patch("imaging_api.routers.projects.get_project", side_effect=NotFoundError("Not found")):
        response = client.get("/projects/BAD_PROJ")

    assert response.status_code == 404


def test_get_project_error():
    with patch("imaging_api.routers.projects.get_project", side_effect=Exception("error")):
        response = client.get("/projects/PROJ1")

    assert response.status_code == 500


# ── GET /projects/{project_id}/subjects ──


def test_get_subjects_success():
    sample_subject = Subject(
        ID="SUBJ1",
        label="Subject 1",
        insert_date="2024-01-01",
        project="PROJ1",
        insert_user="admin",
        URI="/data/subjects/SUBJ1",
    )
    with patch("imaging_api.routers.projects.get_subjects", return_value=[sample_subject]):
        response = client.get("/projects/PROJ1/subjects")

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_subjects_not_found():
    with patch("imaging_api.routers.projects.get_subjects", side_effect=NotFoundError("Not found")):
        response = client.get("/projects/BAD_PROJ/subjects")

    assert response.status_code == 404


def test_get_subjects_error():
    with patch("imaging_api.routers.projects.get_subjects", side_effect=Exception("error")):
        response = client.get("/projects/PROJ1/subjects")

    assert response.status_code == 500


# ── GET /projects/{project_id}/experiments ──


def test_get_experiments_success():
    sample_experiment = Experiment(
        ID="EXP1",
        label="Experiment 1",
        date="2024-01-01",
        project="PROJ1",
        insert_date="2024-01-01",
        xsiType="xnat:mrSessionData",
        URI="/data/experiments/EXP1",
    )
    with patch("imaging_api.routers.projects.get_experiments", return_value=[sample_experiment]):
        response = client.get("/projects/PROJ1/experiments")

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_experiments_not_found():
    with patch("imaging_api.routers.projects.get_experiments", side_effect=NotFoundError("Not found")):
        response = client.get("/projects/BAD_PROJ/experiments")

    assert response.status_code == 404


def test_get_experiments_error():
    with patch("imaging_api.routers.projects.get_experiments", side_effect=Exception("error")):
        response = client.get("/projects/PROJ1/experiments")

    assert response.status_code == 500


# ── GET /projects/{project_id}/experiment/{experiment_id_or_label} ──


def test_get_experiment_success():
    mock_data = {"items": [{"data_fields": {"ID": "EXP1"}}]}
    with patch("imaging_api.routers.projects.get_experiment", return_value=mock_data):
        response = client.get("/projects/PROJ1/experiment/EXP1")

    assert response.status_code == 200


def test_get_experiment_not_found():
    with patch("imaging_api.routers.projects.get_experiment", side_effect=NotFoundError("Not found")):
        response = client.get("/projects/PROJ1/experiment/BAD_EXP")

    assert response.status_code == 404


def test_get_experiment_error():
    with patch("imaging_api.routers.projects.get_experiment", side_effect=Exception("error")):
        response = client.get("/projects/PROJ1/experiment/EXP1")

    assert response.status_code == 500
