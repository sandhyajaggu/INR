"""Fix frozen created_at/updated_at defaults

The initial schema declared these defaults as server_default='now()' (a
quoted string), so PostgreSQL stored the literal 'now()' cast to a
timestamp once, at table-creation time (2026-08-27 05:16:22 UTC). Every
row inserted since got that same timestamp instead of its real one. This
resets each default to the now() function. Existing rows keep the frozen
value; their real creation times were never recorded.

Revision ID: e5a7c93b1d24
Revises: d8e2b6c41f07
Create Date: 2026-09-29 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e5a7c93b1d24'
down_revision: Union[str, None] = 'd8e2b6c41f07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TIMESTAMP_COLUMNS = [
    ('achievements', 'created_at'),
    ('activity_log', 'created_at'),
    ('beneficiaries', 'created_at'),
    ('beneficiaries', 'updated_at'),
    ('booths', 'created_at'),
    ('contact_messages', 'created_at'),
    ('development_works', 'created_at'),
    ('development_works', 'updated_at'),
    ('mandals', 'created_at'),
    ('notes_followups', 'created_at'),
    ('schemes', 'created_at'),
    ('staff_users', 'created_at'),
    ('staff_users', 'updated_at'),
    ('villages', 'created_at'),
    ('voters', 'created_at'),
    ('voters', 'updated_at'),
]


def upgrade() -> None:
    for table, column in TIMESTAMP_COLUMNS:
        op.alter_column(table, column, server_default=sa.text('now()'))


def downgrade() -> None:
    # Intentionally a no-op: going back would re-freeze every default to a
    # fixed timestamp, which is the bug this revision fixes.
    pass
