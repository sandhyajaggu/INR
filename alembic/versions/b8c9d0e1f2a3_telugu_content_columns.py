"""Telugu text for public website content (te JSONB on events, works, media)

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-11-12 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ('events', 'development_works', 'press_gallery', 'media_albums', 'videos', 'mp3_songs')


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column('te', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    for table in TABLES:
        op.drop_column(table, 'te')
