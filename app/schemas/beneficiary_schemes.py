"""Per-scheme beneficiary schemas.

Each of the 7 welfare schemes has a genuinely different Add/Edit form per
the functional spec (docs/INR_MLA_CRM_Project_Documentation.docx section
5.4.3-5.4.9) — different field names, different optional/required sets, and
a different subset of scheme_details. Rather than hide that behind one
generic `scheme_details: dict` blob, each scheme gets its own Create/Update/
Out schema with those fields as real top-level fields. All still write to
the single shared `beneficiaries` table (app/core/beneficiary_scheme_router.py
maps each scheme's fields onto that table's columns + scheme_details) — the
DB design from db/schema.sql is unchanged, this is purely an API-layer
ergonomics improvement.
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


# --- CM Relief Fund (cmrf) — no scheme_details fields --------------------


class CmrfCreate(BaseModel):
    beneficiary_name: str
    relation_name: str | None = None
    epic_no: str | None = None
    amount: Decimal | None = None
    mandal_name: str
    village_name: str
    application_date: date | None = None
    status: str = Field(default="pending", pattern="^(pending|approved|rejected|disbursed)$")
    video_url: str | None = None
    remarks: str | None = None


class CmrfUpdate(CmrfCreate):
    pass


class CmrfOut(ORMModel):
    id: int
    beneficiary_name: str
    relation_name: str | None
    epic_no: str | None
    voter_id: int | None
    amount: Decimal | None
    mandal_id: int
    village_id: int
    application_date: date | None
    status: str
    video_url: str | None
    remarks: str | None
    created_at: datetime
    updated_at: datetime


# --- Aadabidda Nidhi (aadabidda_nidhi) — no scheme_details fields --------


class AadabiddaNidhiCreate(BaseModel):
    beneficiary_name: str
    relation_name: str | None = None
    epic_no: str | None = None
    age: int | None = None
    aadhaar_number: str | None = None
    mobile_number: str | None = None
    bank_account_number: str | None = None
    ifsc_code: str | None = None
    amount: Decimal | None = Field(default=None, description="Monthly amount")
    mandal_name: str
    village_name: str
    application_date: date | None = None
    status: str = Field(default="pending", pattern="^(pending|approved|rejected|disbursed)$")
    photo_url: str | None = None
    document_url: str | None = None
    remarks: str | None = None


class AadabiddaNidhiUpdate(AadabiddaNidhiCreate):
    pass


class AadabiddaNidhiOut(ORMModel):
    id: int
    beneficiary_name: str
    relation_name: str | None
    epic_no: str | None
    voter_id: int | None
    age: int | None
    aadhaar_masked: str | None = None
    mobile_number: str | None
    bank_account_number: str | None
    ifsc_code: str | None
    amount: Decimal | None
    mandal_id: int
    village_id: int
    application_date: date | None
    status: str
    photo_url: str | None
    document_url: str | None
    remarks: str | None
    created_at: datetime
    updated_at: datetime


# --- Thalliki Vandanam (thalliki_vandanam) -------------------------------


class ThallikiVandanamCreate(BaseModel):
    mother_name: str
    relation_name: str | None = None
    epic_no: str | None = None
    student_name: str
    school_name: str
    class_grade: str
    aadhaar_number: str | None = None
    mobile_number: str | None = None
    bank_account_number: str | None = None
    ifsc_code: str | None = None
    amount: Decimal | None = Field(default=None, description="Annual amount")
    mandal_name: str
    village_name: str
    application_date: date | None = None
    status: str = Field(default="pending", pattern="^(pending|approved|rejected|disbursed)$")
    photo_url: str | None = None
    document_url: str | None = None
    remarks: str | None = None


class ThallikiVandanamUpdate(ThallikiVandanamCreate):
    pass


class ThallikiVandanamOut(ORMModel):
    id: int
    mother_name: str
    relation_name: str | None
    epic_no: str | None
    voter_id: int | None
    student_name: str
    school_name: str
    class_grade: str
    aadhaar_masked: str | None = None
    mobile_number: str | None
    bank_account_number: str | None
    ifsc_code: str | None
    amount: Decimal | None
    mandal_id: int
    village_id: int
    application_date: date | None
    status: str
    photo_url: str | None
    document_url: str | None
    remarks: str | None
    created_at: datetime
    updated_at: datetime


# --- Deepam Scheme (deepam_scheme) — free gas connection, no amount ------


class DeepamSchemeCreate(BaseModel):
    head_of_household_name: str
    relation_name: str | None = None
    ration_card_number: str
    gas_connection_number: str
    gas_agency: str
    aadhaar_number: str | None = None
    epic_no: str | None = None
    mobile_number: str | None = None
    mandal_name: str
    village_name: str
    application_date: date | None = None
    status: str = Field(default="pending", pattern="^(pending|approved|rejected|disbursed)$")
    photo_url: str | None = None
    document_url: str | None = None
    remarks: str | None = None


class DeepamSchemeUpdate(DeepamSchemeCreate):
    pass


class DeepamSchemeOut(ORMModel):
    id: int
    head_of_household_name: str
    relation_name: str | None
    ration_card_number: str
    gas_connection_number: str
    gas_agency: str
    aadhaar_masked: str | None = None
    epic_no: str | None
    voter_id: int | None
    mobile_number: str | None
    mandal_id: int
    village_id: int
    application_date: date | None
    status: str
    photo_url: str | None
    document_url: str | None
    remarks: str | None
    created_at: datetime
    updated_at: datetime


# --- Maha Shakthi / Free Bus Travel (maha_shakthi) — no amount ----------


class MahaShakthiCreate(BaseModel):
    beneficiary_name: str
    relation_name: str | None = None
    age: int | None = None
    aadhaar_number: str | None = None
    mobile_number: str | None = None
    bus_pass_number: str
    preferred_route: str | None = None
    depot: str | None = None
    mandal_name: str
    village_name: str
    application_date: date | None = None
    status: str = Field(default="pending", pattern="^(pending|approved|rejected|disbursed)$")
    photo_url: str | None = None
    document_url: str | None = None
    remarks: str | None = None


class MahaShakthiUpdate(MahaShakthiCreate):
    pass


class MahaShakthiOut(ORMModel):
    id: int
    beneficiary_name: str
    relation_name: str | None
    age: int | None
    aadhaar_masked: str | None = None
    mobile_number: str | None
    bus_pass_number: str
    preferred_route: str | None
    depot: str | None
    mandal_id: int
    village_id: int
    application_date: date | None
    status: str
    photo_url: str | None
    document_url: str | None
    remarks: str | None
    created_at: datetime
    updated_at: datetime


# --- Annadata Sukhibhava (annadata_sukhibhava) ---------------------------


class AnnadataSukhibhavaCreate(BaseModel):
    farmer_name: str
    relation_name: str | None = None
    land_extent_acres: float
    survey_number: str
    aadhaar_number: str | None = None
    epic_no: str | None = None
    mobile_number: str | None = None
    bank_account_number: str | None = None
    ifsc_code: str | None = None
    amount: Decimal | None = Field(default=None, description="Annual amount")
    mandal_name: str
    village_name: str
    application_date: date | None = None
    status: str = Field(default="pending", pattern="^(pending|approved|rejected|disbursed)$")
    photo_url: str | None = None
    document_url: str | None = None
    remarks: str | None = None


class AnnadataSukhibhavaUpdate(AnnadataSukhibhavaCreate):
    pass


class AnnadataSukhibhavaOut(ORMModel):
    id: int
    farmer_name: str
    relation_name: str | None
    land_extent_acres: float | None = None
    survey_number: str | None = None
    aadhaar_masked: str | None = None
    epic_no: str | None
    voter_id: int | None
    mobile_number: str | None
    bank_account_number: str | None
    ifsc_code: str | None
    amount: Decimal | None
    mandal_id: int
    village_id: int
    application_date: date | None
    status: str
    photo_url: str | None
    document_url: str | None
    remarks: str | None
    created_at: datetime
    updated_at: datetime


# --- Yuvagalam (yuvagalam) -----------------------------------------------


class YuvagalamCreate(BaseModel):
    beneficiary_name: str
    relation_name: str | None = None
    epic_no: str | None = None
    age: int | None = None
    qualification: str
    aadhaar_number: str | None = None
    mobile_number: str | None = None
    bank_account_number: str | None = None
    ifsc_code: str | None = None
    amount: Decimal | None = Field(default=None, description="Monthly allowance")
    mandal_name: str
    village_name: str
    application_date: date | None = None
    status: str = Field(default="pending", pattern="^(pending|approved|rejected|disbursed)$")
    photo_url: str | None = None
    document_url: str | None = None
    remarks: str | None = None


class YuvagalamUpdate(YuvagalamCreate):
    pass


class YuvagalamOut(ORMModel):
    id: int
    beneficiary_name: str
    relation_name: str | None
    epic_no: str | None
    voter_id: int | None
    age: int | None
    qualification: str | None = None
    aadhaar_masked: str | None = None
    mobile_number: str | None
    bank_account_number: str | None
    ifsc_code: str | None
    amount: Decimal | None
    mandal_id: int
    village_id: int
    application_date: date | None
    status: str
    photo_url: str | None
    document_url: str | None
    remarks: str | None
    created_at: datetime
    updated_at: datetime
