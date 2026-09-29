"""Add booth party-vote and status columns

Revision ID: c3f1a9d2e7b4
Revises: bd846982c801
Create Date: 2026-09-29 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c3f1a9d2e7b4'
down_revision: Union[str, None] = 'bd846982c801'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('booths', sa.Column('tdp_votes', sa.Integer(), server_default=sa.text('0'), nullable=False))
    op.add_column('booths', sa.Column('ysp_votes', sa.Integer(), server_default=sa.text('0'), nullable=False))
    op.add_column('booths', sa.Column('janasena_votes', sa.Integer(), server_default=sa.text('0'), nullable=False))
    op.add_column('booths', sa.Column('status', sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column('booths', 'status')
    op.drop_column('booths', 'janasena_votes')
    op.drop_column('booths', 'ysp_votes')
    op.drop_column('booths', 'tdp_votes')
