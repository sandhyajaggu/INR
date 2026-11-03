"""Voters page fields, removed voters, Families, booth agents, Polling Day

- voters: relation type, religion, caste, alternate mobile, date of birth,
  status (Verified/Pending), mobile verified flag, soft removal (reason,
  details, who/when) and Polling Day marking (status, party, when, by whom)
- families + family_members (one family per voter)
- booths: Telugu name, agent alternate mobile, agent photo, updated_at

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-11-03 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- voters ------------------------------------------------------------
    op.add_column('voters', sa.Column('relation_type', sa.String(10), nullable=True))
    op.add_column('voters', sa.Column('religion', sa.String(30), nullable=True))
    op.add_column('voters', sa.Column('caste_category', sa.String(20), nullable=True))
    op.add_column('voters', sa.Column('alt_mobile', sa.String(15), nullable=True))
    op.add_column('voters', sa.Column('dob', sa.Date(), nullable=True))
    op.add_column('voters', sa.Column('status', sa.String(20), server_default='Pending', nullable=False))
    op.add_column('voters', sa.Column('mobile_verified', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('voters', sa.Column('removed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('voters', sa.Column('removal_reason', sa.String(50), nullable=True))
    op.add_column('voters', sa.Column('removal_details', sa.Text(), nullable=True))
    op.add_column('voters', sa.Column('removed_by', sa.String(150), nullable=True))
    op.add_column('voters', sa.Column('polling_status', sa.String(20), server_default='not_voted', nullable=False))
    op.add_column('voters', sa.Column('voted_party', sa.String(30), nullable=True))
    op.add_column('voters', sa.Column('marked_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('voters', sa.Column('marked_by', sa.String(150), nullable=True))
    op.create_check_constraint('ck_voters_status', 'voters', "status IN ('Verified','Pending')")
    op.create_check_constraint('ck_voters_polling_status', 'voters', "polling_status IN ('voted','not_voted')")
    op.create_index('idx_voters_removed_at', 'voters', ['removed_at'])
    op.create_index('idx_voters_booth_id', 'voters', ['booth_id'])
    op.create_index('idx_voters_mandal_id', 'voters', ['mandal_id'])
    op.create_index('idx_voters_dob', 'voters', ['dob'])

    # --- families ----------------------------------------------------------
    op.create_table(
        'families',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('head_voter_id', sa.Integer(), sa.ForeignKey('voters.id', ondelete='CASCADE'), nullable=False),
        sa.Column('head_name', sa.String(150), nullable=False),
        sa.Column('mobile', sa.String(15), nullable=True),
        sa.Column('mandal_id', sa.Integer(), sa.ForeignKey('mandals.id'), nullable=True),
        sa.Column('village_id', sa.Integer(), sa.ForeignKey('villages.id'), nullable=True),
        sa.Column('booth_no', sa.String(20), nullable=True),
        sa.Column('members_count', sa.Integer(), server_default='1', nullable=False),
        sa.Column('schemes_availed', sa.Integer(), server_default='0', nullable=False),
        sa.Column('children_under_18', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('head_voter_id', name='uq_families_head_voter_id'),
    )
    op.create_table(
        'family_members',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('family_id', sa.Integer(), sa.ForeignKey('families.id', ondelete='CASCADE'), nullable=False),
        sa.Column('voter_id', sa.Integer(), sa.ForeignKey('voters.id', ondelete='CASCADE'), nullable=False),
        sa.Column('relation', sa.String(30), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('voter_id', name='uq_family_members_voter_id'),
    )
    op.create_index('idx_family_members_family_id', 'family_members', ['family_id'])

    # --- booths ------------------------------------------------------------
    op.add_column('booths', sa.Column('booth_name_te', sa.String(200), nullable=True))
    op.add_column('booths', sa.Column('agent_alt_mobile', sa.String(15), nullable=True))
    op.add_column('booths', sa.Column('agent_photo', sa.Text(), nullable=True))
    op.add_column(
        'booths',
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )


def downgrade() -> None:
    for column in ('updated_at', 'agent_photo', 'agent_alt_mobile', 'booth_name_te'):
        op.drop_column('booths', column)
    op.drop_index('idx_family_members_family_id', table_name='family_members')
    op.drop_table('family_members')
    op.drop_table('families')
    for index in ('idx_voters_dob', 'idx_voters_mandal_id', 'idx_voters_booth_id', 'idx_voters_removed_at'):
        op.drop_index(index, table_name='voters')
    op.drop_constraint('ck_voters_polling_status', 'voters', type_='check')
    op.drop_constraint('ck_voters_status', 'voters', type_='check')
    for column in (
        'marked_by', 'marked_at', 'voted_party', 'polling_status', 'removed_by', 'removal_details',
        'removal_reason', 'removed_at', 'mobile_verified', 'status', 'dob', 'alt_mobile',
        'caste_category', 'religion', 'relation_type',
    ):
        op.drop_column('voters', column)
