"""Settings page: Telugu profile, preferences, Telugu mandal/village names

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-11-03 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TELUGU = {
    'Kandukur': 'కందుకూరు',
    'Lingasamudram': 'లింగసముద్రం',
    'Gudluru': 'గుడ్లూరు',
    'Ulavapadu': 'ఉలవపాడు',
    'Voletivaripalem': 'వోలేటివారిపాలెం',
}


def upgrade() -> None:
    op.add_column('mandals', sa.Column('name_te', sa.String(150), nullable=True))
    op.add_column('villages', sa.Column('name_te', sa.String(150), nullable=True))
    mandals = sa.table('mandals', sa.column('name', sa.String), sa.column('name_te', sa.String))
    for name, te in TELUGU.items():
        op.execute(mandals.update().where(mandals.c.name == name).values(name_te=te))
    op.add_column('app_settings', sa.Column('profile_te', postgresql.JSONB(), nullable=True))
    op.add_column('app_settings', sa.Column('preferences', postgresql.JSONB(), nullable=True))
    op.alter_column('app_settings', 'contact_phone', existing_type=sa.String(15), type_=sa.String(150))


def downgrade() -> None:
    op.execute("UPDATE app_settings SET contact_phone = left(contact_phone, 15)")
    op.alter_column('app_settings', 'contact_phone', existing_type=sa.String(150), type_=sa.String(15))
    op.drop_column('app_settings', 'preferences')
    op.drop_column('app_settings', 'profile_te')
    op.drop_column('villages', 'name_te')
    op.drop_column('mandals', 'name_te')
