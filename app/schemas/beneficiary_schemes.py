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

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import (
    ORMModel,
    coerce_excel_cell_to_str,
    validate_aadhaar_number,
    validate_mobile_number,
)


def _require_valid_aadhaar(v: object) -> str:
    validated = validate_aadhaar_number(v)
    if validated is None:
        raise ValueError("aadhaar_number is required")
    return validated


def _require_valid_mobile(v: object) -> str:
    validated = validate_mobile_number(v)
    if validated is None:
        raise ValueError("mobile_number is required")
    return validated


# --- CM Relief Fund (cmrf) — no scheme_details fields --------------------


class CmrfCreate(BaseModel):
    beneficiary_name: str
    relation_name: str
    epic_no: str
    amount: Decimal = Field(gt=0)
    mandal_name: str
    village_name: str
    application_date: date
    status: str = Field(pattern="^(pending|approved|rejected|disbursed)$")
    video_url: str
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
    mandal_name: str | None = None
    village_id: int
    village_name: str | None = None
    application_date: date | None
    status: str
    video_url: str | None
    remarks: str | None
    created_at: datetime
    updated_at: datetime


# --- Aadabidda Nidhi (aadabidda_nidhi) — no scheme_details fields --------


class AadabiddaNidhiCreate(BaseModel):
    beneficiary_name: str
    relation_name: str
    epic_no: str
    age: int
    aadhaar_number: str
    mobile_number: str
    bank_account_number: str
    ifsc_code: str
    amount: Decimal = Field(gt=0, description="Monthly amount")
    mandal_name: str
    village_name: str
    application_date: date
    status: str = Field(pattern="^(pending|approved|rejected|disbursed)$")
    photo_url: str
    document_url: str | None = None
    remarks: str | None = None

    @field_validator("bank_account_number", "ifsc_code", mode="before")
    @classmethod
    def _coerce_numeric_cells(cls, v: object) -> object:
        return coerce_excel_cell_to_str(v)

    @field_validator("aadhaar_number", mode="before")
    @classmethod
    def _validate_aadhaar(cls, v: object) -> str:
        return _require_valid_aadhaar(v)

    @field_validator("mobile_number", mode="before")
    @classmethod
    def _validate_mobile(cls, v: object) -> str:
        return _require_valid_mobile(v)


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
    mandal_name: str | None = None
    village_id: int
    village_name: str | None = None
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
    relation_name: str
    epic_no: str
    student_name: str
    school_name: str
    class_grade: str
    aadhaar_number: str
    mobile_number: str
    bank_account_number: str
    ifsc_code: str
    amount: Decimal = Field(gt=0, description="Annual amount")
    mandal_name: str
    village_name: str
    application_date: date
    status: str = Field(pattern="^(pending|approved|rejected|disbursed)$")
    photo_url: str
    document_url: str | None = None
    remarks: str | None = None

    @field_validator("bank_account_number", "ifsc_code", mode="before")
    @classmethod
    def _coerce_numeric_cells(cls, v: object) -> object:
        return coerce_excel_cell_to_str(v)

    @field_validator("aadhaar_number", mode="before")
    @classmethod
    def _validate_aadhaar(cls, v: object) -> str:
        return _require_valid_aadhaar(v)

    @field_validator("mobile_number", mode="before")
    @classmethod
    def _validate_mobile(cls, v: object) -> str:
        return _require_valid_mobile(v)


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
    mandal_name: str | None = None
    village_id: int
    village_name: str | None = None
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
    relation_name: str
    ration_card_number: str
    gas_connection_number: str
    gas_agency: str
    aadhaar_number: str
    epic_no: str
    mobile_number: str
    mandal_name: str
    village_name: str
    application_date: date
    status: str = Field(pattern="^(pending|approved|rejected|disbursed)$")
    photo_url: str
    document_url: str | None = None
    remarks: str | None = None

    @field_validator("ration_card_number", "gas_connection_number", mode="before")
    @classmethod
    def _coerce_numeric_cells(cls, v: object) -> object:
        return coerce_excel_cell_to_str(v)

    @field_validator("aadhaar_number", mode="before")
    @classmethod
    def _validate_aadhaar(cls, v: object) -> str:
        return _require_valid_aadhaar(v)

    @field_validator("mobile_number", mode="before")
    @classmethod
    def _validate_mobile(cls, v: object) -> str:
        return _require_valid_mobile(v)


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
    mandal_name: str | None = None
    village_id: int
    village_name: str | None = None
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
    relation_name: str
    age: int
    aadhaar_number: str
    mobile_number: str
    bus_pass_number: str
    preferred_route: str
    depot: str
    mandal_name: str
    village_name: str
    application_date: date
    status: str = Field(pattern="^(pending|approved|rejected|disbursed)$")
    photo_url: str
    document_url: str | None = None
    remarks: str | None = None

    @field_validator("bus_pass_number", mode="before")
    @classmethod
    def _coerce_numeric_cells(cls, v: object) -> object:
        return coerce_excel_cell_to_str(v)

    @field_validator("aadhaar_number", mode="before")
    @classmethod
    def _validate_aadhaar(cls, v: object) -> str:
        return _require_valid_aadhaar(v)

    @field_validator("mobile_number", mode="before")
    @classmethod
    def _validate_mobile(cls, v: object) -> str:
        return _require_valid_mobile(v)


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
    mandal_name: str | None = None
    village_id: int
    village_name: str | None = None
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
    relation_name: str
    land_extent_acres: float
    survey_number: str
    aadhaar_number: str
    epic_no: str
    mobile_number: str
    bank_account_number: str
    ifsc_code: str
    amount: Decimal = Field(gt=0, description="Annual amount")
    mandal_name: str
    village_name: str
    application_date: date
    status: str = Field(pattern="^(pending|approved|rejected|disbursed)$")
    photo_url: str
    document_url: str | None = None
    remarks: str | None = None

    @field_validator("survey_number", "bank_account_number", "ifsc_code", mode="before")
    @classmethod
    def _coerce_numeric_cells(cls, v: object) -> object:
        return coerce_excel_cell_to_str(v)

    @field_validator("aadhaar_number", mode="before")
    @classmethod
    def _validate_aadhaar(cls, v: object) -> str:
        return _require_valid_aadhaar(v)

    @field_validator("mobile_number", mode="before")
    @classmethod
    def _validate_mobile(cls, v: object) -> str:
        return _require_valid_mobile(v)


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
    mandal_name: str | None = None
    village_id: int
    village_name: str | None = None
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
    relation_name: str
    epic_no: str
    age: int
    qualification: str
    aadhaar_number: str
    mobile_number: str
    bank_account_number: str
    ifsc_code: str
    amount: Decimal = Field(gt=0, description="Monthly allowance")
    mandal_name: str
    village_name: str
    application_date: date
    status: str = Field(pattern="^(pending|approved|rejected|disbursed)$")
    photo_url: str
    document_url: str | None = None
    remarks: str | None = None

    @field_validator("bank_account_number", "ifsc_code", mode="before")
    @classmethod
    def _coerce_numeric_cells(cls, v: object) -> object:
        return coerce_excel_cell_to_str(v)

    @field_validator("aadhaar_number", mode="before")
    @classmethod
    def _validate_aadhaar(cls, v: object) -> str:
        return _require_valid_aadhaar(v)

    @field_validator("mobile_number", mode="before")
    @classmethod
    def _validate_mobile(cls, v: object) -> str:
        return _require_valid_mobile(v)


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
    mandal_name: str | None = None
    village_id: int
    village_name: str | None = None
    application_date: date | None
    status: str
    photo_url: str | None
    document_url: str | None
    remarks: str | None
    created_at: datetime
    updated_at: datetime
