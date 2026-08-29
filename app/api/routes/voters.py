from fastapi import APIRouter, HTTPException, Query, UploadFile, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.dependencies import CurrentUser, DbSession, RequireStaff, RequireSuperAdmin
from app.models.voters import Voter
from app.schemas.bulk_import import BulkImportResult
from app.schemas.common import PaginatedResponse
from app.schemas.voters import GenderDistribution, MandalVoterSummary, VoterCreate, VoterOut, VoterUpdate
from app.services.activity_service import log_activity
from app.services.encryption_service import encrypt_aadhaar
from app.services.excel_import_service import parse_excel_rows
from app.services.geography_service import resolve_geography
from app.services.voter_service import bulk_import_voters, get_voter_or_404, search_voters, to_voter_out

router = APIRouter(prefix="/voters", tags=["Voters"])


@router.get("", response_model=PaginatedResponse[VoterOut], summary="Search/list voters")
async def list_voters(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    epic_no: str | None = Query(None, description="Exact EPIC number match"),
    name: str | None = Query(None, description="Fuzzy name search (pg_trgm)"),
    mandal_id: int | None = Query(None),
    village_id: int | None = Query(None),
    booth_id: int | None = Query(None),
    gender: str | None = Query(None, pattern="^(Male|Female|Other)$"),
) -> PaginatedResponse[VoterOut]:
    return await search_voters(
        db,
        page=page,
        page_size=page_size,
        epic_no=epic_no,
        name=name,
        mandal_id=mandal_id,
        village_id=village_id,
        booth_id=booth_id,
        gender=gender,
    )


@router.get(
    "/summary/by-mandal",
    response_model=list[MandalVoterSummary],
    summary="Mandal-wise voter summary (v_mandal_voter_summary)",
)
async def voter_summary_by_mandal(db: DbSession, current_user: CurrentUser) -> list[MandalVoterSummary]:
    result = await db.execute(
        text(
            "SELECT mandal_id, mandal_name, male_voters, female_voters, total_voters, pct_of_total "
            "FROM v_mandal_voter_summary ORDER BY mandal_name"
        )
    )
    return [MandalVoterSummary(**row._mapping) for row in result]


@router.get(
    "/gender-distribution",
    response_model=list[GenderDistribution],
    summary="Voter gender distribution (v_voter_gender_distribution)",
)
async def voter_gender_distribution(db: DbSession, current_user: CurrentUser) -> list[GenderDistribution]:
    result = await db.execute(text("SELECT gender, total FROM v_voter_gender_distribution"))
    return [GenderDistribution(gender=row.gender, total=row.total) for row in result]


@router.get("/{voter_id}", response_model=VoterOut, summary="Get one voter")
async def get_voter(voter_id: int, db: DbSession, current_user: CurrentUser) -> VoterOut:
    voter = await get_voter_or_404(db, voter_id)
    return to_voter_out(voter)


@router.post("", response_model=VoterOut, status_code=status.HTTP_201_CREATED, summary="Add a voter")
async def create_voter(
    payload: VoterCreate, db: DbSession, current_user: RequireStaff
) -> VoterOut:
    data = payload.model_dump()
    data["epic_no"] = data["epic_no"].upper()
    mandal_name = data.pop("mandal_name")
    village_name = data.pop("village_name")
    data["mandal_id"], data["village_id"] = await resolve_geography(
        db, mandal_name=mandal_name, village_name=village_name
    )
    if data.get("aadhaar_number"):
        data["aadhaar_number"] = encrypt_aadhaar(data["aadhaar_number"])

    voter = Voter(**data)
    db.add(voter)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "epic_no already exists") from exc

    await log_activity(
        db,
        actor_id=current_user.id,
        action_type="voter_added",
        module="voters",
        reference_id=voter.id,
        description=f"Voter '{voter.name}' ({voter.epic_no}) added",
    )
    await db.commit()
    await db.refresh(voter)
    return to_voter_out(voter)


@router.post(
    "/bulk-upload",
    response_model=BulkImportResult,
    summary="Bulk-import voters from an Excel (.xlsx) sheet",
    description=(
        "All-or-nothing import: every row is validated first (required fields, "
        "epic_no format, no duplicate epic_no within the file or against existing "
        "voters, mandal_name/village_name/booth_number all resolvable). If any row "
        "fails, nothing is written and the full list of row errors is returned instead."
    ),
)
async def bulk_upload_voters(
    file: UploadFile, db: DbSession, current_user: RequireStaff
) -> BulkImportResult:
    rows = await parse_excel_rows(
        file, required_columns={"epic_no", "name", "mandal_name", "village_name"}
    )
    result = await bulk_import_voters(db, rows, actor_id=current_user.id)
    if result.errors:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=[e.model_dump() for e in result.errors]
        )
    return result


@router.put("/{voter_id}", response_model=VoterOut, summary="Update a voter")
async def update_voter(
    voter_id: int,
    payload: VoterUpdate,
    db: DbSession,
    current_user: RequireStaff,
) -> VoterOut:
    voter = await get_voter_or_404(db, voter_id)
    data = payload.model_dump()
    data["epic_no"] = data["epic_no"].upper()
    mandal_name = data.pop("mandal_name")
    village_name = data.pop("village_name")
    data["mandal_id"], data["village_id"] = await resolve_geography(
        db, mandal_name=mandal_name, village_name=village_name
    )
    if data.get("aadhaar_number"):
        data["aadhaar_number"] = encrypt_aadhaar(data["aadhaar_number"])

    for field, value in data.items():
        setattr(voter, field, value)

    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "epic_no already exists") from exc

    await log_activity(
        db,
        actor_id=current_user.id,
        action_type="voter_updated",
        module="voters",
        reference_id=voter.id,
        description=f"Voter '{voter.name}' ({voter.epic_no}) updated",
    )
    await db.commit()
    await db.refresh(voter)
    return to_voter_out(voter)


@router.delete(
    "/{voter_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a voter (super_admin only)",
)
async def delete_voter(
    voter_id: int, db: DbSession, current_user: RequireSuperAdmin
) -> None:
    voter = await get_voter_or_404(db, voter_id)
    await log_activity(
        db,
        actor_id=current_user.id,
        action_type="voter_deleted",
        module="voters",
        reference_id=voter.id,
        description=f"Voter '{voter.name}' ({voter.epic_no}) deleted",
    )
    await db.delete(voter)
    await db.commit()


@router.get(
    "/{voter_id}/aadhaar/reveal",
    summary="Reveal a voter's plaintext Aadhaar (super_admin only)",
)
async def reveal_voter_aadhaar(
    voter_id: int, db: DbSession, current_user: RequireSuperAdmin
) -> dict[str, str | None]:
    from app.services.encryption_service import decrypt_aadhaar

    voter = await get_voter_or_404(db, voter_id)
    return {"aadhaar_number": decrypt_aadhaar(voter.aadhaar_number) if voter.aadhaar_number else None}
