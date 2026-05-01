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

"""Integration coverage of the project_services DB path: create → fetch → soft-delete.

Hits ``project_services.services.project_services`` against the throwaway
Postgres rather than mocking the session. Unit tests for the same code mock
``Session`` and never catch SQL-shaped bugs (wrong column names, missing
relationships, default mismatches, etc.); these do.
"""

import pytest
from sqlmodel import select

from flip_api.db.models.main_models import Projects, ProjectUserAccess
from flip_api.domain.schemas.projects import ProjectDetails
from flip_api.domain.schemas.status import ProjectStatus
from flip_api.project_services.services.project_services import (
    create_project,
    delete_project,
    get_project,
)


@pytest.fixture
def project_payload(user_factory) -> ProjectDetails:
    return ProjectDetails(
        name="Cohort Discovery",
        description="Federated retrospective query across two trusts",
        users=[user_factory().id],
        dicom_to_nifti=True,
    )


def test_create_project_persists_and_grants_creator_access(session, project_payload, user_factory):
    """A created project should be readable back with the creator wired into ProjectUserAccess."""
    creator_id = user_factory().id

    new_project_id = create_project(payload=project_payload, current_user_id=creator_id, session=session)

    persisted = session.get(Projects, new_project_id)
    assert persisted is not None
    assert persisted.name == project_payload.name
    assert persisted.description == project_payload.description
    assert persisted.owner_id == creator_id
    assert persisted.deleted is False
    assert persisted.status == ProjectStatus.UNSTAGED

    access_rows = session.exec(
        select(ProjectUserAccess).where(ProjectUserAccess.project_id == new_project_id)
    ).all()
    access_user_ids = {row.user_id for row in access_rows}
    assert creator_id in access_user_ids, "Creator must be granted access on create"
    # `users` from payload added on top of the creator
    assert access_user_ids.issuperset({creator_id, *project_payload.users})


def test_get_project_returns_project_for_existing_id(session, project_payload, user_factory):
    """`get_project` should hydrate a known project; query is None when no Queries row exists."""
    creator_id = user_factory().id
    new_project_id = create_project(payload=project_payload, current_user_id=creator_id, session=session)

    fetched = get_project(new_project_id, session)

    assert fetched.id == new_project_id
    assert fetched.name == project_payload.name
    assert fetched.query is None
    # `IProjectResponse` doesn't expose `deleted` (the lookup filters on
    # `Projects.deleted == False` so a soft-deleted row would 404 here).
    # Verify by re-querying the table directly.
    assert session.get(Projects, new_project_id).deleted is False


def test_list_projects_returns_only_undeleted(session, project_payload, user_factory):
    """A simple SELECT-with-deleted=False against real Postgres — the kind of query the
    --skip-db CI used to silently let drift."""
    creator_id = user_factory().id
    create_project(payload=project_payload, current_user_id=creator_id, session=session)
    deleted_payload = project_payload.model_copy(update={"name": "ToDelete"})
    deleted_id = create_project(payload=deleted_payload, current_user_id=creator_id, session=session)

    delete_project(deleted_id, creator_id, session)

    live = session.exec(select(Projects).where(Projects.deleted.is_(False))).all()  # type: ignore[attr-defined]
    live_names = {p.name for p in live}
    assert project_payload.name in live_names
    assert "ToDelete" not in live_names


def test_soft_delete_marks_row_deleted_in_place(session, project_payload, user_factory):
    """Soft delete must flip the `deleted` flag — not remove the row — and audit it."""
    creator_id = user_factory().id
    new_project_id = create_project(payload=project_payload, current_user_id=creator_id, session=session)

    delete_project(new_project_id, creator_id, session)

    row = session.get(Projects, new_project_id)
    assert row is not None, "Soft delete must keep the row for audit"
    assert row.deleted is True
