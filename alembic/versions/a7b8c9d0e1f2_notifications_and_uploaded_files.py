"""Notifications (dashboard bell) and uploaded_files (Files CRUD)

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-11-12 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('staff_users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('link', sa.String(300), nullable=True),
        sa.Column('page_key', sa.String(50), nullable=True),
        sa.Column('reference_id', sa.String(50), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('staff_users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_notifications_user_unread', 'notifications', ['user_id', 'is_read', 'created_at'])

    op.create_table(
        'uploaded_files',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('url', sa.Text(), nullable=False, unique=True),
        sa.Column('subfolder', sa.String(50), nullable=False),
        sa.Column('original_name', sa.String(255), nullable=True),
        sa.Column('content_type', sa.String(100), nullable=True),
        sa.Column('size_bytes', sa.Integer(), nullable=True),
        sa.Column('uploaded_by', sa.Integer(), sa.ForeignKey('staff_users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_uploaded_files_subfolder', 'uploaded_files', ['subfolder'])


def downgrade() -> None:
    op.drop_index('ix_uploaded_files_subfolder', table_name='uploaded_files')
    op.drop_table('uploaded_files')
    op.drop_index('ix_notifications_user_unread', table_name='notifications')
    op.drop_table('notifications')
