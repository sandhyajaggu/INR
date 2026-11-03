"""Voters page (frontend: Voters.js, AddVoterModal, VoterDetailsDrawer, UploadVotersModal).

    GET    /voters                      list (paginated; items in the frontend's voter shape)
    GET    /voters/stats                cards: total / male / female / thirdGender / newVoters / removed
    GET    /voters/removed              listRemovedVoters()
    POST   /voters                      add (AddVoterModal payload)
    PUT    /voters/{id}                 edit
    POST   /voters/{id}/remove          removeVoter(id, reason)       -> {"success": true}
    POST   /voters/bulk-remove          remove several                -> {"success": true, "removed": n}
    POST   /voters/{id}/restore         restoreVoter(id)              -> {"success": true}
    POST   /voters/{id}/mark-voted      mark as voted (optional party)
    POST   /voters/bulk-upload          .xlsx / .xls / .csv (frontend template headers accepted)
    GET    /voters/bulk-upload/template
    DELETE /voters/{id}                 permanent delete (super_admin)

`{id}` is the numeric id or the EPIC number. With ~2.3 lakh voters the list
is paginated server-side; it supports the page's search (`q`), card filter
(`filter` = male / female / third / new) and column sort (`sort_key`,
`sort_dir`). Results respect the user's scope (mandal / booth).
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.dependencies import DbSession, RequireSuperAdmin, page_access
from app.core.scope import resolve_scope
from app.models.voters import Voter
from app.schemas.bulk_import import BulkImportResult, capped_error_detail
from app.schemas.voters import (
    VOTER_HEADER_ALIASES,
    GenderDistribution,
    MandalVoterSummary,
    MarkVotedRequest,
    VoterBulkRemoveRequest,
    VoterCreate,
    VoterRemoveRequest,
    VoterStats,
    VoterUpdate,
)
from app.services.activity_service import diff_changes, log_activity
from app.services.excel_import_service import parse_upload_rows
from app.services.voter_profile import voter_rows
from app.services.voter_service import (
    bulk_import_voters,
    get_voter_or_404,
    list_removed_voters,
    remove_voter,
    restore_voter,
    search_voters,
    set_polling_mark,
    voter_stats,
    voter_values,
)
from app.services.voter_template_service import build_voter_template

router = APIRouter(prefix="/voters", tags=["Voters"])

CanView = page_access("voters", "view")
CanEdit = page_access("voters", "edit")
CanDelete = page_access("voters", "admin")

AUDITED_FIELDS = (
    "epic_no", "name", "relation_type", "relation_name", "gender", "age", "religion", "caste_category",
    "mandal", "village", "booth_no", "mobile", "alt_mobile", "voted_last_election", "is_new_voter",
    "status", "dob",
)


def _audit_view(row: dict[str, Any]) -> dict[str, Any]:
    return {k: row.get(k) for k in AUDITED_FIELDS}


@router.get("", summary="List voters (paginated, frontend voter shape)")
async def list_voters(
    db: DbSession,
    current_user: CanView,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    q: str | None = Query(None, description="Search EPIC, name, relation, mobile, mandal, village, booth"),
    filter: str | None = Query(None, pattern="^(all|male|female|third|new)$", description="Card filter"),
    gender: str | None = Query(None, description="M / F / Third gender (or Male / Female / Other)"),
    epic_no: str | None = Query(None),
    name: str | None = Query(None),
    mandal: str | None = Query(None, description="Mandal name"),
    village: str | None = Query(None, description="Village name"),
    booth_no: str | None = Query(None, description="Booth number, e.g. 256 or #256"),
    mandal_id: int | None = Query(None),
    village_id: int | None = Query(None),
    booth_id: int | None = Query(None),
    status_filter: str | None = Query(None, alias="status", pattern="^(Verified|Pending)$"),
    sort_key: str | None = Query(None),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
) -> dict[str, Any]:
    return await search_voters(
        db,
        scope=await resolve_scope(db, current_user),
        page=page,
        page_size=page_size,
        q=q,
        filter_key=filter,
        gender=gender,
        epic_no=epic_no,
        name=name,
        mandal=mandal,
        village=village,
        booth_no=booth_no,
        mandal_id=mandal_id,
        village_id=village_id,
        booth_id=booth_id,
        status_filter=status_filter,
        sort_key=sort_key,
        sort_dir=sort_dir,
    )


@router.get("/stats", response_model=VoterStats, summary="Voters page summary cards")
async def get_voter_stats(db: DbSession, current_user: CanView) -> dict[str, int]:
    return await voter_stats(db, await resolve_scope(db, current_user))


@router.get("/removed", summary="Removed voters (newest first)")
async def get_removed_voters(
    db: DbSession, current_user: CanView, limit: int = Query(1000, ge=1, le=10000)
) -> list[dict[str, Any]]:
    return await list_removed_voters(db, await resolve_scope(db, current_user), limit)


@router.get(
    "/summary/by-mandal",
    response_model=list[MandalVoterSummary],
    summary="Mandal-wise voter summary (v_mandal_voter_summary)",
)
async def voter_summary_by_mandal(db: DbSession, current_user: CanView) -> list[MandalVoterSummary]:
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
async def voter_gender_distribution(db: DbSession, current_user: CanView) -> list[GenderDistribution]:
    result = await db.execute(text("SELECT gender, total FROM v_voter_gender_distribution"))
    return [GenderDistribution(gender=row.gender, total=row.total) for row in result]


XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get(
    "/bulk-upload/template",
    summary="Download the voters upload template (.xlsx)",
    response_class=Response,
    responses={200: {"content": {XLSX_MEDIA_TYPE: {}}}},
)
async def download_voter_template(db: DbSession, current_user: CanEdit) -> Response:
    return Response(
        content=await build_voter_template(db),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": 'attachment; filename="voters_template.xlsx"'},
    )


@router.post(
    "/bulk-upload",
    response_model=BulkImportResult,
    summary="Bulk-import voters from .xlsx / .xls / .csv",
    description=(
        "Accepts the frontend template (EPIC No, Full Name, Relation Type, Relation Name, Gender, Age, "
        "Religion, Caste Category, Mandal, Village, Booth No, Mobile, Alternate Mobile, Voted Last "
        "Election, Is New Voter, Status, Date of Birth) or the older snake_case headers. All-or-nothing: "
        "if any row fails nothing is written and the row errors are returned. An existing EPIC No "
        "updates that voter."
    ),
)
async def bulk_upload_voters(file: UploadFile, db: DbSession, current_user: CanEdit) -> BulkImportResult:
    rows = await parse_upload_rows(
        file, required_columns={"epic_no", "name", "mandal", "village"}, aliases=VOTER_HEADER_ALIASES
    )
    result = await bulk_import_voters(db, rows, actor_id=current_user.id)
    if result.errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=capped_error_detail(result.errors))
    return result


@router.post("/bulk-remove", summary="Remove several voters (same reason)")
async def bulk_remove_voters(
    payload: VoterBulkRemoveRequest, db: DbSession, current_user: CanDelete
) -> dict[str, Any]:
    removed = 0
    for voter_id in payload.ids:
        voter = await get_voter_or_404(db, voter_id)
        if voter.removed_at is None:
            await remove_voter(db, voter, reason=payload.reason, details=payload.details, actor=current_user)
            removed += 1
    await db.commit()
    return {"success": True, "removed": removed}


@router.get("/{voter_id}", summary="Get one voter (id or EPIC number)")
async def get_voter(voter_id: str, db: DbSession, current_user: CanView) -> dict[str, Any]:
    voter = await get_voter_or_404(db, voter_id)
    return (await voter_rows(db, [voter]))[0]


@router.post("", status_code=status.HTTP_201_CREATED, summary="Add a voter")
async def create_voter(payload: VoterCreate, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    voter = Voter(**await voter_values(db, payload))
    db.add(voter)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "A voter with this EPIC number already exists") from exc
    await log_activity(
        db,
        actor_id=current_user.id,
        action_type="voter_added",
        module="voters",
        reference_id=voter.id,
        description=f"Added voter {voter.epic_no} ({voter.name})",
    )
    await db.commit()
    await db.refresh(voter)
    return (await voter_rows(db, [voter]))[0]


@router.put("/{voter_id}", summary="Update a voter")
async def update_voter(
    voter_id: str, payload: VoterUpdate, db: DbSession, current_user: CanEdit
) -> dict[str, Any]:
    voter = await get_voter_or_404(db, voter_id)
    before = _audit_view((await voter_rows(db, [voter]))[0])
    for field, value in (await voter_values(db, payload)).items():
        setattr(voter, field, value)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "A voter with this EPIC number already exists") from exc
    await db.refresh(voter)
    after_row = (await voter_rows(db, [voter]))[0]
    await log_activity(
        db,
        actor_id=current_user.id,
        action_type="voter_updated",
        module="voters",
        reference_id=voter.id,
        description=f"Updated voter {voter.epic_no}",
        changes=diff_changes(before, _audit_view(after_row)),
    )
    await db.commit()
    return after_row


@router.post("/{voter_id}/remove", summary="Remove a voter (reason: Shifted / Died / ...)")
async def remove_one_voter(
    voter_id: str, db: DbSession, current_user: CanDelete, payload: VoterRemoveRequest | None = None
) -> dict[str, Any]:
    payload = payload or VoterRemoveRequest()
    voter = await get_voter_or_404(db, voter_id)
    await remove_voter(db, voter, reason=payload.reason, details=payload.details, actor=current_user)
    await db.commit()
    return {"success": True}


@router.post("/{voter_id}/restore", summary="Restore a removed voter")
async def restore_one_voter(voter_id: str, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    voter = await get_voter_or_404(db, voter_id)
    await restore_voter(db, voter, actor=current_user)
    await db.commit()
    return {"success": True}


@router.post("/{voter_id}/mark-voted", summary="Mark a voter as voted (Voters page / drawer)")
async def mark_voter_voted(
    voter_id: str, db: DbSession, current_user: CanEdit, payload: MarkVotedRequest | None = None
) -> dict[str, Any]:
    voter = await get_voter_or_404(db, voter_id, include_removed=False)
    set_polling_mark(voter, voted=True, party=payload.party if payload else None, marked_by=current_user.name)
    await log_activity(
        db,
        actor_id=current_user.id,
        action_type="voter_marked_voted",
        module="voters",
        reference_id=voter.id,
        description=f"Marked voter {voter.epic_no} as voted",
    )
    await db.commit()
    await db.refresh(voter)
    return (await voter_rows(db, [voter]))[0]


@router.delete("/{voter_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Permanently delete a voter")
async def delete_voter(voter_id: str, db: DbSession, current_user: RequireSuperAdmin) -> None:
    voter = await get_voter_or_404(db, voter_id)
    await log_activity(
        db,
        actor_id=current_user.id,
        action_type="voter_deleted",
        module="voters",
        reference_id=voter.id,
        description=f"Deleted voter {voter.epic_no}",
    )
    await db.delete(voter)
    await db.commit()


@router.get("/{voter_id}/aadhaar/reveal", summary="Reveal a voter's plaintext Aadhaar (super_admin only)")
async def reveal_voter_aadhaar(voter_id: str, db: DbSession, current_user: RequireSuperAdmin) -> dict[str, str | None]:
    from app.services.encryption_service import decrypt_aadhaar

    voter = await get_voter_or_404(db, voter_id)
    return {"aadhaar_number": decrypt_aadhaar(voter.aadhaar_number) if voter.aadhaar_number else None}

