"""Row shape for the booths upload (frontend: BoothModals.jsx UploadBoothsModal).

Template columns: Booth No, Polling Station, Voters, Mandal, Village,
Agent Name, Agent Mobile, Agent Alt Mobile. Same rules as the Add Booth
form: everything except Agent Alt Mobile is required.
"""

from pydantic import ConfigDict, field_validator

from app.schemas.common import coerce_excel_cell_to_str
from app.schemas.geography import BoothCreate

# Sheet header (as shown in the template) -> BoothCreate key.
BOOTH_SHEET_COLUMNS: dict[str, str] = {
    "Booth No": "booth_no",
    "Polling Station": "name",
    "Voters": "voters",
    "Mandal": "mandal",
    "Village": "village",
    "Agent Name": "agent_name",
    "Agent Mobile": "agent_mobile",
    "Agent Alt Mobile": "agent_alt_mobile",
}
BOOTH_COLUMN_LABELS = {key: label for label, key in BOOTH_SHEET_COLUMNS.items()}

# Normalized header -> BoothCreate key (template headers plus common variants).
BOOTH_HEADER_ALIASES: dict[str, str] = {
    "polling_station": "name",
    "booth_name": "name",
    "station_name": "name",
    "booth_number": "booth_no",
    "registered_votes": "voters",
    "total_voters": "voters",
    "in_charge": "agent_name",
    "agent": "agent_name",
    "agent_alternate_mobile": "agent_alt_mobile",
    "mandal_name": "mandal",
    "village_name": "village",
}


class BoothBulkRow(BoothCreate):
    model_config = ConfigDict(extra="ignore")

    @field_validator("agent_mobile", "agent_alt_mobile", mode="before")
    @classmethod
    def _numeric_mobile(cls, v: object) -> object:
        return coerce_excel_cell_to_str(v)
