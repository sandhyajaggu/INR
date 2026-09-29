"""Voters bulk-upload template (.xlsx) for POST /voters/bulk-upload.

A blank template with example rows, not a pre-filled export: the voter roll
(~230k rows) is far larger than one download or one upload (capped at
MAX_ROWS_PER_SHEET) can hold. Headers normalize to exactly the keys
VoterBulkRow expects ("EPIC No" -> epic_no, ...). The "Voters" sheet is the
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
    ["ABC1234567", "Ravi Kumar", "Venkat Rao", 42, "Male", "9876543210", "123412341234", "4-12",
     "Kandukur", "Palukur", "81", "Yes", "No"],
    ["XYZ7654321", "Lakshmi Devi", "Srinivas", 19, "Female", None, None, "7-3A",
     "Lingasamudram", "Chinapavani", "59", None, "Yes"],
]


def voter_template_columns(mandals: list[str]) -> list[TemplateColumn]:
    yes_no = ["Yes", "No"]
    return [
        TemplateColumn("EPIC No", True, "3 letters + 7 digits, e.g. ABC1234567. An existing EPIC No updates that voter.", as_text=True),
        TemplateColumn("Name", True, "Voter's full name"),
        TemplateColumn("Relation Name", False, "Father / husband name"),
        TemplateColumn("Age", False, "Whole number, 0-130"),
        TemplateColumn("Gender", False, "Male, Female or Other", choices=["Male", "Female", "Other"]),
        TemplateColumn("Mobile", False, "10 digits, starts with 6-9", as_text=True),
        TemplateColumn("Aadhaar Number", False, "Exactly 12 digits (stored encrypted)", as_text=True),
        TemplateColumn("House No", False, "As printed on the roll", as_text=True),
        TemplateColumn("Mandal Name", True, "One of the mandals in the dropdown", choices=mandals or None),
        TemplateColumn("Village Name", True, "Village in that mandal"),
        TemplateColumn("Booth Number", False, "Must already exist in that mandal (Booths page)", as_text=True),
        TemplateColumn("Voted Last Election", False, "Yes or No", choices=yes_no),
        TemplateColumn("Is New Voter", False, "Yes or No (blank = No)", choices=yes_no),
    ]


async def build_voter_template(db: AsyncSession) -> bytes:
    spec = TemplateSheet("Voters", voter_template_columns(await mandal_names(db)), EXAMPLE_ROWS)
    return build_single_sheet_template(spec, standard_notes())
