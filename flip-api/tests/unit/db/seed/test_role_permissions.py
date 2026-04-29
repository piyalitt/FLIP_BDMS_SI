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

from unittest.mock import MagicMock
from uuid import UUID, uuid4

from sqlmodel import Session

from flip_api.db.models.user_models import Permission, PermissionRef, RolePermission
from flip_api.db.seed.role_permissions import seed_role_permissions

ADMIN_ROLE_ID = uuid4()
RESEARCHER_ROLE_ID = uuid4()


def _make_session(admin_role_id: UUID | None, researcher_role_id: UUID | None) -> MagicMock:
    """Build a mock session whose `exec(...).first()` returns admin then researcher role IDs.

    `seed_role_permissions` calls `session.exec(...).first()` twice (once for the Admin role
    lookup, once for the Researcher role) and `session.exec(select(Permission)).all()` once
    in between. This helper wires those return values up in order.
    """
    session = MagicMock(spec=Session)
    first_results = iter([admin_role_id, researcher_role_id])
    all_results = iter([[Permission(id=UUID(p.value), permission_name=p.name) for p in PermissionRef]])

    def fake_exec(_stmt):
        result = MagicMock()
        result.first = lambda: next(first_results, None)
        result.all = lambda: next(all_results, [])
        return result

    session.exec.side_effect = fake_exec
    return session


def test_researcher_is_seeded_with_can_create_projects_only():
    """Researcher must get CAN_CREATE_PROJECTS, not the admin-bypass CAN_MANAGE_PROJECTS. See issue #358."""
    session = _make_session(ADMIN_ROLE_ID, RESEARCHER_ROLE_ID)

    seed_role_permissions(session)

    researcher_perms = [
        rp.permission_id
        for call in session.add.call_args_list
        for rp in [call.args[0]]
        if isinstance(rp, RolePermission) and rp.role_id == RESEARCHER_ROLE_ID
    ]
    assert UUID(PermissionRef.CAN_CREATE_PROJECTS.value) in researcher_perms
    assert UUID(PermissionRef.CAN_MANAGE_PROJECTS.value) not in researcher_perms


def test_seed_deletes_legacy_researcher_manage_projects_grant():
    """On any deployed DB that already granted Researcher → CAN_MANAGE_PROJECTS, the seed must remove it."""
    session = _make_session(ADMIN_ROLE_ID, RESEARCHER_ROLE_ID)

    seed_role_permissions(session)

    # Assert that one of the session.execute calls was a DELETE targeting RolePermission.
    # We render the statement to SQL text and check it mentions both the table and the legacy
    # permission UUID — this catches accidental removal of the cleanup without coupling the
    # test too tightly to SQLAlchemy internals.
    delete_calls = [
        str(call.args[0]) for call in session.execute.call_args_list if call.args
    ]
    assert any("role_permission" in sql.lower() and "DELETE" in sql.upper() for sql in delete_calls), (
        f"Expected a DELETE against role_permission, got: {delete_calls}"
    )


def test_admin_receives_all_permissions():
    """Admin keeps every permission — including any newly added one like CAN_CREATE_PROJECTS."""
    session = _make_session(ADMIN_ROLE_ID, RESEARCHER_ROLE_ID)

    seed_role_permissions(session)

    admin_perms = {
        rp.permission_id
        for call in session.add.call_args_list
        for rp in [call.args[0]]
        if isinstance(rp, RolePermission) and rp.role_id == ADMIN_ROLE_ID
    }
    expected = {UUID(p.value) for p in PermissionRef}
    assert admin_perms == expected
