"""Add village_aliases table

Revision ID: bd846982c801
Revises: 7e55ce0a46f5
Create Date: 2026-09-01 12:55:57.361584

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'bd846982c801'
down_revision: Union[str, None] = '7e55ce0a46f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'village_aliases',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('village_id', sa.Integer(), nullable=False),
        sa.Column('mandal_id', sa.Integer(), nullable=False),
        sa.Column('alias', sa.String(length=150), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['mandal_id'], ['mandals.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['village_id'], ['villages.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('mandal_id', 'alias'),
    )
    op.create_index('idx_village_aliases_village', 'village_aliases', ['village_id'])


def downgrade() -> None:
    op.drop_index('idx_village_aliases_village', table_name='village_aliases')
    op.drop_table('village_aliases')
