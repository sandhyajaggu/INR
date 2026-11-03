"""Voters bulk-upload template (.xlsx) for POST /voters/bulk-upload.

A blank template with example rows, not a pre-filled export: the voter roll
(~230k rows) is far larger than one download or one upload (capped at
MAX_ROWS_PER_SHEET) can hold. Headers normalize to exactly the keys
VoterBulkRow expects (via VOTER_HEADER_ALIASES: "Full Name" -> name, ...). The "Voters" sheet is the
active one, which is the sheet the upload reads; "Instructions" follows it.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.bulk_template_service import (
    TemplateColumn,
    TemplateSheet,
    build_single_sheet_template,
    mandal_names,
    standard_notes,
)

EXAMPLE_ROWS = [
    ["INR1234587", "Lakshmi Devi", "W/o", "Subba Rao", "F", 28, "Christian", "SC", "Lingasamudram",
     "Chinapavani", "256", "9876543210", None, "No", "Yes", "Verified", "1998-05-12", None, "4-12"],
    ["ABC1234567", "Ravi Kumar", "S/o", "Venkat Rao", "M", 42, "Hindu", "BC-A", "Kandukur",
     "Kandukur Town", None, None, None, "Yes", "No", "Pending", None, None, None],
]


def voter_template_columns(mandals: list[str]) -> list[TemplateColumn]:
    yes_no = ["Yes", "No"]
    return [
        TemplateColumn("EPIC No", True, "3 letters + 7 digits, e.g. ABC1234567. An existing EPIC No updates that voter.", as_text=True),
        TemplateColumn("Full Name", True, "Voter's full name"),
        TemplateColumn("Relation Type", False, "S/o, W/o, D/o or H/o", choices=["S/o", "W/o", "D/o", "H/o"]),
        TemplateColumn("Relation Name", False, "Father / husband name"),
        TemplateColumn("Gender", False, "M, F or Third gender", choices=["M", "F", "Third gender"]),
        TemplateColumn("Age", False, "Whole number, 0-130"),
        TemplateColumn("Religion", False, "Hindu, Muslim, Christian or Other", choices=["Hindu", "Muslim", "Christian", "Other"]),
        TemplateColumn("Caste Category", False, "OC, BC-A ... BC-E, SC, ST, Minority",
                       choices=["OC", "BC-A", "BC-B", "BC-C", "BC-D", "BC-E", "SC", "ST", "Minority"]),
        TemplateColumn("Mandal", True, "One of the mandals in the dropdown", choices=mandals or None),
        TemplateColumn("Village", True, "Village in that mandal"),
        TemplateColumn("Booth No", False, "Must already exist in that mandal (Booths page)", as_text=True),
        TemplateColumn("Mobile", False, "10 digits, starts with 6-9", as_text=True),
        TemplateColumn("Alternate Mobile", False, "10 digits, starts with 6-9", as_text=True),
        TemplateColumn("Voted Last Election", False, "Yes or No", choices=yes_no),
        TemplateColumn("Is New Voter", False, "Yes or No (blank = No)", choices=yes_no),
        TemplateColumn("Status", False, "Verified or Pending (blank = Pending)", choices=["Verified", "Pending"]),
        TemplateColumn("Date of Birth", False, "YYYY-MM-DD or DD/MM/YYYY", as_text=True),
        TemplateColumn("Aadhaar Number", False, "Exactly 12 digits (stored encrypted)", as_text=True),
        TemplateColumn("House No", False, "As printed on the roll", as_text=True),
    ]


async def build_voter_template(db: AsyncSession) -> bytes:
    spec = TemplateSheet("Voters", voter_template_columns(await mandal_names(db)), EXAMPLE_ROWS)
    return build_single_sheet_template(spec, standard_notes())
