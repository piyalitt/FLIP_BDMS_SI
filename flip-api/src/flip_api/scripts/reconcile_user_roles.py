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

"""One-off cleanup of ghost ``user_role`` rows whose ``user_id`` is not in Cognito.

Historically ``delete_user`` only deleted the Cognito user, leaving role
grants behind in ``user_role``. The same PR that introduces this script
fixes ``delete_user`` to drop role grants too, so this script exists to
reconcile any *legacy* ghosts produced before that fix landed. It must run
*before* the follow-up migration that drops the local ``users`` table and
removes the FK that used to guard ``user_role`` (planned filename
``2026-05-06_drop_users_table.sql``, not yet committed).

This script lists every Cognito sub in the configured user pool, walks the
``user_role`` table, and deletes any row whose ``user_id`` is not in that
set. Each deletion is logged for audit. Refuses to delete if Cognito
returned zero users while ghosts exist — that almost certainly means a
Cognito read failure rather than a genuinely empty pool, and proceeding
would wipe every legitimate role grant.

Usage:
    uv run python -m flip_api.scripts.reconcile_user_roles
    uv run python -m flip_api.scripts.reconcile_user_roles --dry-run
"""

import argparse
from uuid import UUID

from sqlmodel import Session, col, delete, select

from flip_api.db.database import engine
from flip_api.db.models.user_models import UserRole
from flip_api.utils.cognito_helpers import get_cognito_users
from flip_api.utils.logger import logger


def reconcile(session: Session, dry_run: bool) -> int:
    """Delete user_role rows whose user_id is not present in Cognito.

    Args:
        session (Session): The SQLModel session used for DB reads/writes.
        dry_run (bool): If True, only log what would be removed; do not delete.

    Returns:
        int: Number of ghost rows found.
    """
    cognito_subs: set[UUID] = {u.id for u in get_cognito_users()}
    logger.info(f"Cognito reports {len(cognito_subs)} active users.")

    rows = session.exec(select(UserRole)).all()
    ghosts = [r for r in rows if r.user_id not in cognito_subs]
    logger.info(f"Found {len(ghosts)} ghost user_role rows out of {len(rows)} total.")

    for ghost in ghosts:
        logger.info(
            f"{'[dry-run] would remove' if dry_run else 'Removing'} ghost role grant: "
            f"user_id={ghost.user_id} role_id={ghost.role_id}"
        )

    if not cognito_subs and ghosts and not dry_run:
        # Cognito returned zero users but ghosts exist — almost certainly a
        # Cognito read failure rather than a genuinely empty pool. Refuse
        # to delete; an operator can rerun once Cognito is healthy.
        logger.error(
            "Cognito returned zero users; refusing to delete %d user_role rows. "
            "Verify Cognito connectivity and rerun.",
            len(ghosts),
        )
        return len(ghosts)

    if not dry_run and ghosts:
        ghost_user_ids = [g.user_id for g in ghosts]
        session.execute(delete(UserRole).where(col(UserRole.user_id).in_(ghost_user_ids)))
        session.commit()
        logger.info(f"Removed {len(ghosts)} ghost user_role rows.")

    return len(ghosts)


def main() -> None:
    """Entry point — open a session, run reconciliation, exit."""
    parser = argparse.ArgumentParser(
        description="Reconcile user_role rows against Cognito; remove rows whose user_id no longer exists."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Log what would be removed without actually deleting.",
    )
    args = parser.parse_args()

    with Session(engine) as session:
        reconcile(session, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
