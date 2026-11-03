"""Media albums, public enquiries + Election Pulse, birthdays, voter surveys

- media_albums (photo albums); press_gallery gets a video link; videos get
  channel / thumbnail / duration / size (MP4 downloads are videos with
  source 'upload'); mp3_songs get a duration label and size, file optional
- public_enquiries: Contact page submissions with optional voter feedback
- message_outbox: every outgoing WhatsApp / SMS / email / voice / push
  message is queued here (provider integration sends them later)
- birthday_wishes, mobile_otps; app_settings.birthday_settings
- survey_campaigns, voter_surveys, war_room_alerts

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-11-03 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOW = sa.text('now()')


def _ts(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=NOW, nullable=False)


def upgrade() -> None:
    # --- media ------------------------------------------------------------------
    op.create_table(
        'media_albums',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('album_date', sa.Date(), nullable=True),
        sa.Column('cover_url', sa.Text(), nullable=True),
        sa.Column('photos', postgresql.JSONB(), server_default='[]', nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('staff_users.id', ondelete='SET NULL'), nullable=True),
        _ts('created_at'),
        _ts('updated_at'),
    )
    op.add_column('press_gallery', sa.Column('video_url', sa.Text(), nullable=True))
    op.add_column('videos', sa.Column('channel', sa.String(150), nullable=True))
    op.add_column('videos', sa.Column('thumbnail_url', sa.Text(), nullable=True))
    op.add_column('videos', sa.Column('duration', sa.String(20), nullable=True))
    op.add_column('videos', sa.Column('file_size', sa.String(30), nullable=True))
    op.add_column('mp3_songs', sa.Column('duration', sa.String(20), nullable=True))
    op.add_column('mp3_songs', sa.Column('file_size', sa.String(30), nullable=True))
    op.alter_column('mp3_songs', 'file_url', existing_type=sa.Text(), nullable=True)

    # --- public enquiries ---------------------------------------------------------
    op.create_table(
        'public_enquiries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('citizen_name', sa.String(150), nullable=False),
        sa.Column('epic_no', sa.String(20), nullable=True),
        sa.Column('voter_id', sa.Integer(), sa.ForeignKey('voters.id', ondelete='SET NULL'), nullable=True),
        sa.Column('constituency', sa.String(100), nullable=True),
        sa.Column('enquiry_type', sa.String(100), nullable=False),
        sa.Column('mandal', sa.String(100), nullable=True),
        sa.Column('village', sa.String(150), nullable=True),
        sa.Column('mobile', sa.String(15), nullable=False),
        sa.Column('email', sa.String(150), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('photo_url', sa.Text(), nullable=True),
        sa.Column('voice_url', sa.Text(), nullable=True),
        sa.Column('voice_duration', sa.String(20), nullable=True),
        sa.Column('status', sa.String(20), server_default='New', nullable=False),
        sa.Column('feedback', postgresql.JSONB(), nullable=True),
        sa.Column('matched_in_voter_list', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        _ts('received_at'),
        _ts('updated_at'),
        sa.CheckConstraint("status IN ('New','In Progress','Resolved')", name='ck_public_enquiries_status'),
    )
    op.create_index('idx_public_enquiries_mobile', 'public_enquiries', ['mobile'])
    op.create_index('idx_public_enquiries_received_at', 'public_enquiries', ['received_at'])

    # --- message outbox -------------------------------------------------------------
    op.create_table(
        'message_outbox',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('channel', sa.String(20), nullable=False),
        sa.Column('recipient', sa.String(200), nullable=False),
        sa.Column('recipient_name', sa.String(150), nullable=True),
        sa.Column('subject', sa.String(255), nullable=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('source', sa.String(50), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(20), server_default='Queued', nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('scheduled_for', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        _ts('created_at'),
        sa.CheckConstraint("channel IN ('whatsapp','sms','email','voice','push')", name='ck_outbox_channel'),
        sa.CheckConstraint(
            "status IN ('Queued','Scheduled','Sent','Delivered','Read','Failed','Cancelled')", name='ck_outbox_status'
        ),
    )
    op.create_index('idx_outbox_source', 'message_outbox', ['source', 'source_id'])
    op.create_index('idx_outbox_status', 'message_outbox', ['status'])

    # --- birthdays / OTP ------------------------------------------------------------
    op.create_table(
        'birthday_wishes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('voter_id', sa.Integer(), sa.ForeignKey('voters.id', ondelete='CASCADE'), nullable=False),
        sa.Column('wish_date', sa.Date(), nullable=False),
        sa.Column('channel', sa.String(20), nullable=False),
        sa.Column('status', sa.String(20), server_default='Scheduled', nullable=False),
        sa.Column('outbox_id', sa.Integer(), sa.ForeignKey('message_outbox.id', ondelete='SET NULL'), nullable=True),
        _ts('created_at'),
        _ts('updated_at'),
        sa.UniqueConstraint('voter_id', 'wish_date', name='uq_birthday_wishes_voter_date'),
    )
    op.create_table(
        'mobile_otps',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('voter_id', sa.Integer(), sa.ForeignKey('voters.id', ondelete='CASCADE'), nullable=False),
        sa.Column('mobile', sa.String(15), nullable=False),
        sa.Column('code_hash', sa.String(255), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        _ts('created_at'),
    )
    op.add_column('app_settings', sa.Column('birthday_settings', postgresql.JSONB(), nullable=True))

    # --- surveys -----------------------------------------------------------------------
    op.create_table(
        'survey_campaigns',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('channel', sa.String(30), nullable=False),
        sa.Column('feedback_filter', sa.String(50), nullable=True),
        sa.Column('target', sa.Integer(), server_default='1000', nullable=False),
        sa.Column('responses', sa.Integer(), server_default='0', nullable=False),
        sa.Column('positive', sa.Integer(), server_default='0', nullable=False),
        sa.Column('negative', sa.Integer(), server_default='0', nullable=False),
        sa.Column('status', sa.String(20), server_default='Running', nullable=False),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('closes_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('questions', postgresql.JSONB(), server_default='[]', nullable=False),
        sa.Column('post_text', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('staff_users.id', ondelete='SET NULL'), nullable=True),
        _ts('created_at'),
        _ts('updated_at'),
    )
    op.create_table(
        'voter_surveys',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('voter_id', sa.Integer(), sa.ForeignKey('voters.id', ondelete='CASCADE'), nullable=False),
        sa.Column('survey_type', sa.String(100), nullable=False),
        sa.Column('part_a', postgresql.JSONB(), server_default='{}', nullable=False),
        sa.Column('answers', postgresql.JSONB(), server_default='[]', nullable=False),
        sa.Column('added_questions', postgresql.JSONB(), server_default='[]', nullable=False),
        sa.Column('party_support', sa.String(30), nullable=True),
        sa.Column('party_member', sa.String(10), nullable=True),
        sa.Column('member_party', sa.String(30), nullable=True),
        sa.Column('membership_id', sa.String(50), nullable=True),
        sa.Column('household_status', sa.String(50), nullable=True),
        sa.Column('escalation', sa.String(50), nullable=True),
        sa.Column('field_notes', sa.Text(), nullable=True),
        sa.Column('feedback', sa.String(20), nullable=True),
        sa.Column('surveyed_by', sa.Integer(), sa.ForeignKey('staff_users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('surveyed_by_name', sa.String(150), nullable=True),
        _ts('created_at'),
    )
    op.create_index('idx_voter_surveys_voter_id', 'voter_surveys', ['voter_id'])
    op.create_table(
        'war_room_alerts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('voter_id', sa.Integer(), sa.ForeignKey('voters.id', ondelete='CASCADE'), nullable=False),
        sa.Column('survey_id', sa.Integer(), sa.ForeignKey('voter_surveys.id', ondelete='SET NULL'), nullable=True),
        sa.Column('escalation', sa.String(50), nullable=False),
        sa.Column('household', sa.String(50), nullable=True),
        sa.Column('field_notes', sa.Text(), nullable=True),
        sa.Column('booth_agent', sa.String(150), nullable=True),
        sa.Column('status', sa.String(30), server_default='Pending Action', nullable=False),
        sa.Column('resolution_notes', sa.Text(), nullable=True),
        _ts('raised_at'),
        _ts('updated_at'),
    )


def downgrade() -> None:
    op.drop_table('war_room_alerts')
    op.drop_index('idx_voter_surveys_voter_id', table_name='voter_surveys')
    op.drop_table('voter_surveys')
    op.drop_table('survey_campaigns')
    op.drop_column('app_settings', 'birthday_settings')
    op.drop_table('mobile_otps')
    op.drop_table('birthday_wishes')
    op.drop_index('idx_outbox_status', table_name='message_outbox')
    op.drop_index('idx_outbox_source', table_name='message_outbox')
    op.drop_table('message_outbox')
    op.drop_index('idx_public_enquiries_received_at', table_name='public_enquiries')
    op.drop_index('idx_public_enquiries_mobile', table_name='public_enquiries')
    op.drop_table('public_enquiries')
    op.execute("UPDATE mp3_songs SET file_url = '' WHERE file_url IS NULL")
    op.alter_column('mp3_songs', 'file_url', existing_type=sa.Text(), nullable=False)
    for column in ('file_size', 'duration'):
        op.drop_column('mp3_songs', column)
    for column in ('file_size', 'duration', 'thumbnail_url', 'channel'):
        op.drop_column('videos', column)
    op.drop_column('press_gallery', 'video_url')
    op.drop_table('media_albums')
