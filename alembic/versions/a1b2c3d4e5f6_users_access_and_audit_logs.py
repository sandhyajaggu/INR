"""User Management roles/page access and Audit Logs details

- staff_users: new 'staff' login role, the User Management role label,
  per-page access map, profile fields (EPIC, mandal, village, address,
  photo, scope), first-sign-in flag and last login time. Email becomes
  optional (the User Management form doesn't require it).
- activity_log: actor name, field changes, screenshot and IP for the
  Audit Logs page.
- created_by / actor_id foreign keys to staff_users now SET NULL on delete,
  so removing a user account doesn't fail on records they created.

Revision ID: a1b2c3d4e5f6
Revises: e5a7c93b1d24
Create Date: 2026-11-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'e5a7c93b1d24'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CREATED_BY_TABLES = [
    'gallery_photos',
    'development_works',
    'events',
    'beneficiaries',
    'notes_followups',
    'surveys',
]


def upgrade() -> None:
    # --- staff_users -------------------------------------------------------
    op.drop_constraint('ck_staff_users_role', 'staff_users', type_='check')
    op.create_check_constraint('ck_staff_users_role', 'staff_users', "role IN ('super_admin','admin','staff')")
    op.alter_column('staff_users', 'email', existing_type=sa.String(150), nullable=True)
    op.add_column('staff_users', sa.Column('display_role', sa.String(50), nullable=True))
    op.add_column('staff_users', sa.Column('epic_no', sa.String(20), nullable=True))
    op.add_column('staff_users', sa.Column('mandal', sa.String(100), nullable=True))
    op.add_column('staff_users', sa.Column('village', sa.String(150), nullable=True))
    op.add_column('staff_users', sa.Column('address', sa.Text(), nullable=True))
    op.add_column('staff_users', sa.Column('photo_url', sa.Text(), nullable=True))
    op.add_column('staff_users', sa.Column('scope', sa.String(100), nullable=True))
    op.add_column('staff_users', sa.Column('access', postgresql.JSONB(), nullable=True))
    op.add_column(
        'staff_users',
        sa.Column('must_change_password', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    )
    op.add_column('staff_users', sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "UPDATE staff_users SET display_role = CASE role WHEN 'super_admin' THEN 'Super Admin' "
        "WHEN 'admin' THEN 'Admin' ELSE 'Staff' END, scope = 'All mandals' WHERE display_role IS NULL"
    )

    # --- activity_log ------------------------------------------------------
    op.add_column('activity_log', sa.Column('actor_name', sa.String(150), nullable=True))
    op.add_column('activity_log', sa.Column('changes', postgresql.JSONB(), nullable=True))
    op.add_column('activity_log', sa.Column('screenshot_url', sa.Text(), nullable=True))
    op.add_column('activity_log', sa.Column('ip_address', sa.String(64), nullable=True))
    op.execute(
        "UPDATE activity_log a SET actor_name = s.name FROM staff_users s "
        "WHERE a.actor_id = s.id AND a.actor_name IS NULL"
    )

    # --- ON DELETE SET NULL for references to staff_users --------------------
    op.drop_constraint('activity_log_actor_id_fkey', 'activity_log', type_='foreignkey')
    op.create_foreign_key(
        'activity_log_actor_id_fkey', 'activity_log', 'staff_users', ['actor_id'], ['id'], ondelete='SET NULL'
    )
    for table in CREATED_BY_TABLES:
        op.drop_constraint(f'{table}_created_by_fkey', table, type_='foreignkey')
        op.create_foreign_key(
            f'{table}_created_by_fkey', table, 'staff_users', ['created_by'], ['id'], ondelete='SET NULL'
        )


def downgrade() -> None:
    for table in CREATED_BY_TABLES:
        op.drop_constraint(f'{table}_created_by_fkey', table, type_='foreignkey')
        op.create_foreign_key(f'{table}_created_by_fkey', table, 'staff_users', ['created_by'], ['id'])
    op.drop_constraint('activity_log_actor_id_fkey', 'activity_log', type_='foreignkey')
    op.create_foreign_key('activity_log_actor_id_fkey', 'activity_log', 'staff_users', ['actor_id'], ['id'])

    for column in ('ip_address', 'screenshot_url', 'changes', 'actor_name'):
        op.drop_column('activity_log', column)

    for column in (
        'last_login_at', 'must_change_password', 'access', 'scope', 'photo_url',
        'address', 'village', 'mandal', 'epic_no', 'display_role',
    ):
        op.drop_column('staff_users', column)
    # The old schema had no 'staff' role and required email: keep those
    # accounts but disable them rather than deleting them.
    op.execute("UPDATE staff_users SET role = 'admin', status = 'inactive' WHERE role = 'staff'")
    op.execute("UPDATE staff_users SET email = 'user' || id || '@no-email.local' WHERE email IS NULL")
    op.alter_column('staff_users', 'email', existing_type=sa.String(150), nullable=False)
    op.drop_constraint('ck_staff_users_role', 'staff_users', type_='check')
    op.create_check_constraint('ck_staff_users_role', 'staff_users', "role IN ('super_admin','admin')")
