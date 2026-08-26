"""Cross-scheme beneficiary schemas (read-only views over the shared table).

Per-scheme create/update field validation now lives in
app/schemas/beneficiary_schemes.py — one typed schema per scheme, each with
its own exact Add/Edit form fields. This file only has what's inherently
cross-scheme: the generic read model, Beneficiary Lookup, and the
by-geography aggregate.
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.schemas.common import ORMModel


class BeneficiaryOut(ORMModel):
    id: int
    scheme_id: int
    voter_id: int | None
    epic_no: str | None
    beneficiary_name: str
    relation_name: str | None
    age: int | None
    gender: str | None
    aadhaar_masked: str | None = None
    mobile_number: str | None
    bank_account_number: str | None
    ifsc_code: str | None
    amount: Decimal | None
    village_id: int
    mandal_id: int
    application_date: date | None
    status: str
    photo_url: str | None
    document_url: str | None
    video_url: str | None
    remarks: str | None
    scheme_details: dict
    created_at: datetime
    updated_at: datetime


class BeneficiaryLookupResult(BaseModel):
    scheme_name: str
    amount: Decimal | None
    date: date | None
    status: str


class BeneficiaryGeographyRow(BaseModel):
    mandal_name: str
    village_name: str
    scheme_name: str
    status: str
    beneficiary_count: int
    total_amount: Decimal | None
