"""Families page request bodies (frontend: Families.jsx and its modals)."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import coerce_excel_cell_to_str, validate_epic_no, validate_mobile_number
from app.services.voter_profile import strip_booth_label


class VoterRef(BaseModel):
    """A voter picked in the UI. The frontend passes the whole voter object; epic is what matters."""

    model_config = ConfigDict(extra="allow")

    epic: str | None = None
    epic_no: str | None = None
    id: int | str | None = None


class FamilyCreate(VoterRef):
    """createFamily(headVoter): the chosen head of family."""


class FamilyMemberAdd(BaseModel):
    """addMemberToFamily(familyId, voter, relation)."""

    model_config = ConfigDict(extra="ignore")

    voter: VoterRef | None = None
    epic: str | None = None
    epic_no: str | None = None
    relation: str = Field(default="Member", max_length=30)

    def voter_ref(self) -> dict:
        if self.voter is not None:
            return self.voter.model_dump()
        return {"epic": self.epic or self.epic_no}


class FamilyMembersBatch(BaseModel):
    """Add several unmapped voters at once (AddMembersToFamilyModal)."""

    voters: list[VoterRef] = Field(min_length=1)
    relation: str = Field(default="Member", max_length=30)


class FamilyUpdate(BaseModel):
    """Edit Family form (all fields) or the drawer (children_under_18 only)."""

    head_name: str | None = Field(default=None, min_length=1, max_length=150)
    members_count: int | None = Field(default=None, ge=1)
    schemes_availed: int | None = Field(default=None, ge=0)
    mobile: str | None = None
    mandal: str | None = None
    village: str | None = None
    booth_no: str | None = None
    children_under_18: int | None = Field(default=None, ge=0)

    @field_validator("mobile", mode="before")
    @classmethod
    def _mobile(cls, v: object) -> str | None:
        return validate_mobile_number(v)


class FamilyBulkRow(BaseModel):
    """One row of the families upload (Family ID, Head Name, Head EPIC, Mandal, Village, Booth No, Mobile)."""

    model_config = ConfigDict(extra="ignore")

    head_epic: str
    head_name: str | None = None
    mandal: str | None = None
    village: str | None = None
    booth_no: str | None = None
    mobile: str | None = None

    @field_validator("head_epic", mode="before")
    @classmethod
    def _epic(cls, v: object) -> str:
        epic = validate_epic_no(v)
        if epic is None:
            raise ValueError("Head EPIC is required")
        return epic

    @field_validator("booth_no", "mobile", "head_name", "mandal", "village", mode="before")
    @classmethod
    def _text(cls, v: object) -> object:
        v = coerce_excel_cell_to_str(v)
        return v.strip() or None if isinstance(v, str) else v

    @field_validator("booth_no")
    @classmethod
    def _booth(cls, v: str | None) -> str | None:
        return strip_booth_label(v)

    @field_validator("mobile")
    @classmethod
    def _mobile(cls, v: str | None) -> str | None:
        return validate_mobile_number(v)


FAMILY_HEADER_ALIASES = {"head_epic_no": "head_epic", "epic": "head_epic", "epic_no": "head_epic", "head_of_family": "head_name"}
