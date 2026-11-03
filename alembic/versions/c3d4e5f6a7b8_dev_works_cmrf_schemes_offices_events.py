"""Development works, CMRF applications, scheme details, Government Offices, events

- development_works: fund source, start/completion dates, progress %,
  contractor (+ Telugu), photo, completed photo; statuses become
  Not Started / In Progress / Completed
- cmrf_applications: the CMRF page's applications (applicant, caste,
  purpose, hospital, amount, status, documents)
- schemes: short code, Telugu name, department, frequency, benefit,
  amount per beneficiary, extra details, other spellings; the six welfare
  schemes take the names the dashboard uses
- government_offices: the Government Offices page
- events: live meeting link, previous meeting links; statuses become
  Scheduled / Upcoming / Completed / Postponed / Cancelled

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-11-03 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEME_DETAILS = [
    # scheme_code, name, short_code, telugu, department, frequency, benefit, amount, extra, spellings, description
    ('aadabidda_nidhi', 'Aadabidda Nidhi', 'AN', 'ఆడబిడ్డ నిధి', 'Women Development', 'Monthly',
     '₹1,500 per month', 1500, 'Age', 'Adabidda Nidhi, Aadabidda Nidi, Aada Bidda Nidhi',
     'Financial assistance for adult women in Kandukur constituency.'),
    ('annadata_sukhibhava', 'Annadatha Sukhibhava', 'AS', 'అన్నదాత సుఖీభవ', 'Agriculture', 'Yearly',
     '₹20,000 per farmer per year', 20000, 'Land (acres), Survey no., Instalment',
     'Annadhatha Sukhibava, Annadata Sukhibhava, Annadatha Sukhibava', 'Investment support for farmers.'),
    ('deepam_scheme', 'Deepam', 'DP', 'దీపం', 'Civil Supplies', 'Yearly', '3 free LPG cylinders a year', 0,
     'Gas connection no., Cylinders received', 'Deepam 2.0, Deepam 2.0 (Free LPG), Free LPG, Deepam Scheme, Deepam Gas Scheme',
     'Free LPG cylinders for eligible households.'),
    ('maha_shakthi', 'Sree Shakthi', 'SS', 'స్త్రీ శక్తి', 'Transport (APSRTC)', 'As needed', 'Free bus travel for women', 0,
     'Travel card no.', 'Stree Shakthi, Stree Shakti, Sri Shakthi, Sree Shakti, Free Bus Travel, Maha Shakthi',
     'Free APSRTC bus travel for women.'),
    ('thalliki_vandanam', 'Thalliki Vandanam', 'TV', 'తల్లికి వందనం', 'School Education', 'Yearly',
     '₹15,000 per child per year', 15000, 'Student name, Class, School',
     'Talliki Vandanam, Thalliki Vandhanam, Talliki Vandhanam', 'Support for mothers of school-going children.'),
    ('yuvagalam', 'Youth Employment', 'YE', 'యువతకు ఉపాధి', 'Skill Development', 'Monthly', '₹3,000 per month', 3000,
     'Qualification', 'Youth Employement, Youth Support, Nirudyoga Bruthi, Nirudyoga Bhruthi, Yuvagalam',
     'Unemployment allowance for educated youth.'),
]


def upgrade() -> None:
    # --- development_works ---------------------------------------------------
    op.drop_constraint('ck_devworks_status', 'development_works', type_='check')
    op.execute(
        "UPDATE development_works SET status = CASE status WHEN 'pending' THEN 'Not Started' "
        "WHEN 'in_progress' THEN 'In Progress' WHEN 'completed' THEN 'Completed' ELSE status END"
    )
    op.alter_column('development_works', 'status', server_default='Not Started')
    op.create_check_constraint(
        'ck_devworks_status', 'development_works', "status IN ('Not Started','In Progress','Completed')"
    )
    op.add_column('development_works', sa.Column('fund_source', sa.String(100), nullable=True))
    op.add_column('development_works', sa.Column('start_date', sa.Date(), nullable=True))
    op.add_column('development_works', sa.Column('completion_date', sa.Date(), nullable=True))
    op.add_column('development_works', sa.Column('progress', sa.Integer(), server_default='0', nullable=False))
    op.add_column('development_works', sa.Column('contractor', sa.String(200), nullable=True))
    op.add_column('development_works', sa.Column('contractor_te', sa.String(200), nullable=True))
    op.add_column('development_works', sa.Column('photo_url', sa.Text(), nullable=True))
    op.add_column('development_works', sa.Column('completed_photo_url', sa.Text(), nullable=True))
    op.execute("UPDATE development_works SET start_date = work_date WHERE start_date IS NULL")
    op.execute("UPDATE development_works SET progress = 100 WHERE status = 'Completed'")
    op.create_check_constraint('ck_devworks_progress', 'development_works', 'progress BETWEEN 0 AND 100')

    # --- cmrf_applications ---------------------------------------------------
    op.create_table(
        'cmrf_applications',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('applicant_name', sa.String(150), nullable=False),
        sa.Column('mobile', sa.String(15), nullable=False),
        sa.Column('caste', sa.String(20), nullable=True),
        sa.Column('purpose', sa.String(100), nullable=False),
        sa.Column('hospital', sa.String(200), nullable=False),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('mandal_id', sa.Integer(), sa.ForeignKey('mandals.id'), nullable=False),
        sa.Column('village_id', sa.Integer(), sa.ForeignKey('villages.id'), nullable=False),
        sa.Column('epic_no', sa.String(20), nullable=True),
        sa.Column('status', sa.String(20), server_default='Pending', nullable=False),
        sa.Column('documents', postgresql.JSONB(), server_default='[]', nullable=False),
        sa.Column('remarks', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('staff_users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('submitted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "status IN ('Pending','Under Review','Approved','Rejected')", name='ck_cmrf_applications_status'
        ),
    )

    # --- schemes ---------------------------------------------------------------
    for column in (
        sa.Column('short_code', sa.String(10), nullable=True),
        sa.Column('telugu_name', sa.String(150), nullable=True),
        sa.Column('department', sa.String(150), nullable=True),
        sa.Column('frequency', sa.String(50), nullable=True),
        sa.Column('benefit', sa.String(200), nullable=True),
        sa.Column('amount_per_beneficiary', sa.Numeric(12, 2), nullable=True),
        sa.Column('extra_details', sa.Text(), nullable=True),
        sa.Column('other_spellings', sa.Text(), nullable=True),
    ):
        op.add_column('schemes', column)
    schemes = sa.table(
        'schemes',
        sa.column('scheme_code', sa.String), sa.column('scheme_name', sa.String), sa.column('short_code', sa.String),
        sa.column('telugu_name', sa.String), sa.column('department', sa.String), sa.column('frequency', sa.String),
        sa.column('benefit', sa.String), sa.column('amount_per_beneficiary', sa.Numeric),
        sa.column('extra_details', sa.Text), sa.column('other_spellings', sa.Text),
        sa.column('short_description', sa.Text),
    )
    for code, name, short, te, dept, freq, benefit, amount, extra, spellings, desc in SCHEME_DETAILS:
        op.execute(
            schemes.update()
            .where(schemes.c.scheme_code == code)
            .values(
                scheme_name=name, short_code=short, telugu_name=te, department=dept, frequency=freq,
                benefit=benefit, amount_per_beneficiary=amount, extra_details=extra, other_spellings=spellings,
                short_description=sa.func.coalesce(schemes.c.short_description, desc),
            )
        )
    op.execute(
        "UPDATE schemes SET short_code = 'CM', telugu_name = 'ముఖ్యమంత్రి సహాయ నిధి', department = 'Chief Minister''s Office', "
        "frequency = 'As needed' WHERE scheme_code = 'cmrf'"
    )

    # --- government_offices ----------------------------------------------------
    op.create_table(
        'government_offices',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('name_te', sa.String(200), nullable=True),
        sa.Column('office_type', sa.String(100), nullable=False),
        sa.Column('type_te', sa.String(150), nullable=True),
        sa.Column('category', sa.String(30), nullable=False),
        sa.Column('mandal_id', sa.Integer(), sa.ForeignKey('mandals.id'), nullable=False),
        sa.Column('village_id', sa.Integer(), sa.ForeignKey('villages.id'), nullable=False),
        sa.Column('address', sa.Text(), nullable=False),
        sa.Column('address_te', sa.Text(), nullable=True),
        sa.Column('contact_number', sa.String(30), nullable=False),
        sa.Column('photo_url', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # --- events --------------------------------------------------------------------
    op.drop_constraint('ck_events_status', 'events', type_='check')
    op.execute(
        "UPDATE events SET status = CASE status WHEN 'upcoming' THEN 'Upcoming' WHEN 'completed' THEN 'Completed' "
        "WHEN 'cancelled' THEN 'Cancelled' ELSE status END"
    )
    op.alter_column('events', 'status', server_default='Scheduled')
    op.create_check_constraint(
        'ck_events_status', 'events', "status IN ('Scheduled','Upcoming','Completed','Postponed','Cancelled')"
    )
    op.add_column('events', sa.Column('live_meeting_link', sa.Text(), nullable=True))
    op.add_column('events', sa.Column('prev_meeting_links', postgresql.JSONB(), server_default='[]', nullable=False))
    op.add_column('events', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('events', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))


def downgrade() -> None:
    for column in ('updated_at', 'created_at', 'prev_meeting_links', 'live_meeting_link'):
        op.drop_column('events', column)
    op.drop_constraint('ck_events_status', 'events', type_='check')
    op.execute(
        "UPDATE events SET status = CASE WHEN status IN ('Scheduled','Upcoming','Postponed') THEN 'upcoming' "
        "WHEN status = 'Completed' THEN 'completed' ELSE 'cancelled' END"
    )
    op.alter_column('events', 'status', server_default='upcoming')
    op.create_check_constraint('ck_events_status', 'events', "status IN ('upcoming','completed','cancelled')")

    op.drop_table('government_offices')
    for column in (
        'other_spellings', 'extra_details', 'amount_per_beneficiary', 'benefit', 'frequency', 'department',
        'telugu_name', 'short_code',
    ):
        op.drop_column('schemes', column)
    op.drop_table('cmrf_applications')

    op.drop_constraint('ck_devworks_progress', 'development_works', type_='check')
    for column in (
        'completed_photo_url', 'photo_url', 'contractor_te', 'contractor', 'progress', 'completion_date',
        'start_date', 'fund_source',
    ):
        op.drop_column('development_works', column)
    op.drop_constraint('ck_devworks_status', 'development_works', type_='check')
    op.execute(
        "UPDATE development_works SET status = CASE status WHEN 'Not Started' THEN 'pending' "
        "WHEN 'In Progress' THEN 'in_progress' ELSE 'completed' END"
    )
    op.alter_column('development_works', 'status', server_default='pending')
    op.create_check_constraint(
        'ck_devworks_status', 'development_works', "status IN ('pending','in_progress','completed')"
    )
