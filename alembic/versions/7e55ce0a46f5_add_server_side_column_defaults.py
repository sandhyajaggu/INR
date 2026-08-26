"""add server-side column defaults

Revision ID: 7e55ce0a46f5
Revises: 36c1a5eee24d
Create Date: 2026-08-26 11:36:13.991795

Hand-trimmed from the autogenerate output: the raw diff also proposed
touching every now()-defaulted created_at/updated_at column. That's a known
Alembic false positive (compare_server_default cannot reliably compare
function-based defaults like now()) — worse, its generated downgrade() baked
in a hardcoded timestamp literal captured at generation time instead of
reverting to now(), which would have been actively harmful if ever run. Only
the genuinely new literal-value defaults (matching db/schema.sql's DEFAULT
clauses that were missing a DB-level server_default) are kept below.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '7e55ce0a46f5'
down_revision: Union[str, None] = '36c1a5eee24d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_STRING_DEFAULTS = [
    ("achievements", "status", "active"),
    ("beneficiaries", "status", "pending"),
    ("contact_messages", "status", "new"),
    ("development_works", "status", "pending"),
    ("events", "status", "upcoming"),
    ("gallery_photos", "status", "active"),
    ("janata_darbar_visits", "status", "pending"),
    ("local_leaders", "status", "active"),
    ("mp3_songs", "status", "active"),
    ("notes_followups", "status", "open"),
    ("press_gallery", "status", "active"),
    ("schemes", "status", "active"),
    ("staff_users", "status", "active"),
    ("surveys", "status", "pending"),
    ("videos", "status", "active"),
]

_TEXT_DEFAULTS = [
    ("booths", "total_voters", "0"),
    ("mp3_songs", "play_count", "0"),
    ("mp3_songs", "download_count", "0"),
    ("voters", "is_new_voter", "false"),
]


def upgrade() -> None:
    for table, column, value in _STRING_DEFAULTS:
        op.alter_column(table, column, existing_type=sa.VARCHAR(length=20), server_default=value, existing_nullable=False)
    for table, column, value in _TEXT_DEFAULTS:
        op.alter_column(table, column, server_default=sa.text(value), existing_nullable=False)
    op.alter_column(
        "beneficiaries", "scheme_details",
        existing_type=sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
        server_default="{}",
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "beneficiaries", "scheme_details",
        existing_type=sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
        server_default=None,
        existing_nullable=False,
    )
    for table, column, _ in reversed(_TEXT_DEFAULTS):
        op.alter_column(table, column, server_default=None, existing_nullable=False)
    for table, column, _ in reversed(_STRING_DEFAULTS):
        op.alter_column(table, column, existing_type=sa.VARCHAR(length=20), server_default=None, existing_nullable=False)
