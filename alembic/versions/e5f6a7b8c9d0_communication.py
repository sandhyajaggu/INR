"""Communication: campaigns, templates, broadcast lists, chats, social posts,
auto replies, voter call logs, team meetings

Every campaign's individual messages live in message_outbox
(source='campaign', source_id=<campaign id>), which is where delivered /
read / failed counts come from.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-11-03 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOW = sa.text('now()')


def _ts(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=NOW, nullable=False)


def _creator() -> sa.Column:
    return sa.Column('created_by', sa.Integer(), sa.ForeignKey('staff_users.id', ondelete='SET NULL'), nullable=True)


def upgrade() -> None:
    op.create_table(
        'comm_campaigns',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('channel', sa.String(20), nullable=False),
        sa.Column('subject', sa.String(255), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('message_type', sa.String(20), nullable=True),
        sa.Column('media_url', sa.Text(), nullable=True),
        sa.Column('sms_type', sa.String(20), nullable=True),
        sa.Column('dlt_template_id', sa.String(50), nullable=True),
        sa.Column('language', sa.String(20), nullable=True),
        sa.Column('target_page', sa.String(50), nullable=True),
        sa.Column('group_ids', postgresql.JSONB(), server_default='[]', nullable=False),
        sa.Column('extra_recipients', postgresql.JSONB(), server_default='[]', nullable=False),
        sa.Column('total_recipients', sa.Integer(), server_default='0', nullable=False),
        sa.Column('status', sa.String(20), server_default='Queued', nullable=False),
        sa.Column('scheduled_for', sa.DateTime(timezone=True), nullable=True),
        _creator(),
        _ts('created_at'),
    )
    op.create_index('idx_comm_campaigns_channel', 'comm_campaigns', ['channel'])
    op.create_table(
        'message_templates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('channel', sa.String(20), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('subject', sa.String(255), nullable=True),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('dlt_id', sa.String(50), nullable=True),
        _creator(),
        _ts('created_at'),
        _ts('updated_at'),
    )
    op.create_table(
        'broadcast_lists',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('made_from', sa.String(100), nullable=True),
        sa.Column('contacts', postgresql.JSONB(), server_default='[]', nullable=False),
        _creator(),
        _ts('created_at'),
        _ts('updated_at'),
    )
    op.create_table(
        'chat_messages',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('mobile', sa.String(15), nullable=False),
        sa.Column('contact_name', sa.String(150), nullable=True),
        sa.Column('direction', sa.String(3), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sent_by', sa.Integer(), sa.ForeignKey('staff_users.id', ondelete='SET NULL'), nullable=True),
        _ts('created_at'),
        sa.CheckConstraint("direction IN ('in','out')", name='ck_chat_messages_direction'),
    )
    op.create_index('idx_chat_messages_mobile', 'chat_messages', ['mobile', 'created_at'])
    op.create_table(
        'social_posts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('channel', sa.String(30), nullable=False),
        sa.Column('post_text', sa.Text(), nullable=False),
        sa.Column('link', sa.Text(), nullable=True),
        sa.Column('survey_id', sa.String(30), nullable=True),
        sa.Column('scheduled_for', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status_type', sa.String(20), server_default='reminder', nullable=False),
        sa.Column('done_at', sa.DateTime(timezone=True), nullable=True),
        _creator(),
        _ts('created_at'),
        sa.CheckConstraint(
            "status_type IN ('scheduled','posted','reminder','failed','cancelled')", name='ck_social_posts_status'
        ),
    )
    op.create_table(
        'auto_replies',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('keyword', sa.String(100), nullable=False),
        sa.Column('channel', sa.String(20), server_default='WhatsApp', nullable=False),
        sa.Column('reply', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('times_used', sa.Integer(), server_default='0', nullable=False),
        _creator(),
        _ts('created_at'),
    )
    op.create_table(
        'voter_calls',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('voter_id', sa.Integer(), sa.ForeignKey('voters.id', ondelete='SET NULL'), nullable=True),
        sa.Column('epic_no', sa.String(20), nullable=True),
        sa.Column('person_name', sa.String(150), nullable=False),
        sa.Column('mobile', sa.String(15), nullable=False),
        sa.Column('village', sa.String(150), nullable=True),
        sa.Column('outcome', sa.String(30), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('logged_by', sa.Integer(), sa.ForeignKey('staff_users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('logged_by_name', sa.String(150), nullable=True),
        _ts('created_at'),
    )
    op.create_index('idx_voter_calls_created_at', 'voter_calls', ['created_at'])
    op.create_table(
        'team_meetings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('meeting_date', sa.Date(), nullable=False),
        sa.Column('meeting_time', sa.Time(), nullable=True),
        sa.Column('link_or_venue', sa.Text(), nullable=True),
        sa.Column('participants', sa.String(200), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), server_default='Upcoming', nullable=False),
        _creator(),
        _ts('created_at'),
        sa.CheckConstraint("status IN ('Upcoming','Completed','Cancelled')", name='ck_team_meetings_status'),
    )


def downgrade() -> None:
    op.drop_table('team_meetings')
    op.drop_index('idx_voter_calls_created_at', table_name='voter_calls')
    op.drop_table('voter_calls')
    op.drop_table('auto_replies')
    op.drop_table('social_posts')
    op.drop_index('idx_chat_messages_mobile', table_name='chat_messages')
    op.drop_table('chat_messages')
    op.drop_table('broadcast_lists')
    op.drop_table('message_templates')
    op.drop_index('idx_comm_campaigns_channel', table_name='comm_campaigns')
    op.drop_table('comm_campaigns')
