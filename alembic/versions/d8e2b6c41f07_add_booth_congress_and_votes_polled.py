"""Add booth congress_votes and votes_polled columns

Revision ID: d8e2b6c41f07
Revises: c3f1a9d2e7b4
Create Date: 2026-09-29 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd8e2b6c41f07'
down_revision: Union[str, None] = 'c3f1a9d2e7b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('booths', sa.Column('congress_votes', sa.Integer(), server_default=sa.text('0'), nullable=False))
    op.add_column('booths', sa.Column('votes_polled', sa.Integer(), server_default=sa.text('0'), nullable=False))


def downgrade() -> None:
    op.drop_column('booths', 'votes_polled')
    op.drop_column('booths', 'congress_votes')
