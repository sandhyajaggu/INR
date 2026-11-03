"""Families page (frontend: Families.jsx, mockFamiliesApi).

    GET    /families                         getFamilies()   (paginated; search / sort / mandal)
    GET    /families/stats                   cards: totalFamilies, mappedVotersCount, unmappedCount, mappedPct, acrossBooths
    GET    /families/unmapped-voters         getUnmappedVoters() (paginated; search / mandal / village / booth)
    POST   /families                         createFamily(headVoter)          body: the voter ({epic})
    GET    /families/{id}                    one family with members
    PUT    /families/{id}  (or PATCH)        updateFamily(id, data)           any subset of the Edit Family fields
    POST   /families/{id}/members            addMemberToFamily(id, voter, relation)
    POST   /families/{id}/members/batch      add several voters at once
    DELETE /families/{id}/members/{epic}     remove a member
    DELETE /families/{id}                    deleteFamily(id)                 -> {"success": true}
    POST   /families/bulk-upload             .xlsx / .xls / .csv (Head EPIC, Mobile, Booth No ...)

Family ids are "FAM-<n>"; path params accept "FAM-12" or "12".
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Query, UploadFile, status
from sqlalchemy import select

from app.core.dependencies import DbSession, page_access
from app.core.scope import resolve_scope
from app.models.voters import Voter
from app.schemas.bulk_import import BulkImportResult, capped_error_detail
from app.schemas.families import (
    FAMILY_HEADER_ALIASES,
    FamilyCreate,
    FamilyMemberAdd,
    FamilyMembersBatch,
    FamilyUpdate,
)
from app.services.activity_service import log_activity
from app.services.excel_import_service import parse_upload_rows
from app.services.family_service import (
    FAMILY_PREFIX,
    add_member,
    apply_family_update,
    bulk_import_families,
    create_family,
    family_rows,
    family_stats,
    find_voter,
    get_family_or_404,
    list_families,
    list_unmapped_voters,
    remove_member,
)
from app.core.ids import format_id

router = APIRouter(prefix="/families", tags=["Families"])

CanView = page_access("families", "view")
CanEdit = page_access("families", "edit")
CanDelete = page_access("families", "admin")


@router.get("", summary="List families (paginated)")
async def get_families(
    db: DbSession,
    current_user: CanView,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    q: str | None = Query(None, description="Search family id, head name, EPIC, mandal, village, mobile"),
    mandal: str | None = Query(None),
    sort_key: str | None = Query(None),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
) -> dict[str, Any]:
    return await list_families(
        db,
        scope=await resolve_scope(db, current_user),
        page=page,
        page_size=page_size,
        q=q,
        mandal=mandal,
        sort_key=sort_key,
        sort_dir=sort_dir,
    )


@router.get("/stats", summary="Families page summary cards")
async def get_family_stats(db: DbSession, current_user: CanView) -> dict[str, Any]:
    return await family_stats(db, await resolve_scope(db, current_user))


@router.get("/unmapped-voters", summary="Voters not yet in any family (paginated)")
async def get_unmapped_voters(
    db: DbSession,
    current_user: CanView,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    q: str | None = Query(None, description="Search name, EPIC, relation"),
    mandal: str | None = Query(None),
    village: str | None = Query(None),
    booth_no: str | None = Query(None),
) -> dict[str, Any]:
    return await list_unmapped_voters(
        db,
        scope=await resolve_scope(db, current_user),
        page=page,
        page_size=page_size,
        q=q,
        mandal=mandal,
        village=village,
        booth_no=booth_no,
    )


@router.post(
    "/bulk-upload",
    response_model=BulkImportResult,
    summary="Create families from a sheet (Head EPIC per row)",
    description=(
        "Columns: Family ID (ignored, ids are assigned), Head Name, Head EPIC (required), Mandal, Village, "
        "Booth No, Mobile. Each row creates a family headed by that voter. All-or-nothing."
    ),
)
async def bulk_upload_families(file: UploadFile, db: DbSession, current_user: CanEdit) -> BulkImportResult:
    rows = await parse_upload_rows(file, required_columns={"head_epic"}, aliases=FAMILY_HEADER_ALIASES)
    result = await bulk_import_families(db, rows, actor_id=current_user.id)
    if result.errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=capped_error_detail(result.errors))
    return result


@router.post("", status_code=status.HTTP_201_CREATED, summary="Create a family from its head voter")
async def post_family(payload: FamilyCreate, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    head = await find_voter(db, payload.model_dump())
    family = await create_family(db, head, actor_id=current_user.id)
    await db.commit()
    family = await get_family_or_404(db, str(family.id))
    return (await family_rows(db, [family]))[0]


@router.get("/{family_id}", summary="Get one family")
async def get_family(family_id: str, db: DbSession, current_user: CanView) -> dict[str, Any]:
    family = await get_family_or_404(db, family_id)
    return (await family_rows(db, [family]))[0]


async def _update(family_id: str, payload: FamilyUpdate, db: DbSession, current_user) -> dict[str, Any]:
    family = await get_family_or_404(db, family_id)
    data = payload.model_dump(exclude_unset=True)
    before = (await family_rows(db, [family]))[0]
    await apply_family_update(db, family, data)
    await db.commit()
    family = await get_family_or_404(db, family_id)
    after = (await family_rows(db, [family]))[0]
    changes = [
        [k, str(before.get(k) if before.get(k) is not None else "—"), str(after.get(k) if after.get(k) is not None else "—")]
        for k in ("head_name", "members_count", "schemes_availed", "mobile", "mandal", "village", "booth_no", "children_under_18")
        if before.get(k) != after.get(k)
    ]
    await log_activity(
        db,
        actor_id=current_user.id,
        action_type="family_updated",
        module="families",
        reference_id=family.id,
        description=f"Updated family {format_id(FAMILY_PREFIX, family.id)}",
        changes=changes,
        commit=True,
    )
    return after


@router.put("/{family_id}", summary="Update a family (any subset of fields)")
async def put_family(family_id: str, payload: FamilyUpdate, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    return await _update(family_id, payload, db, current_user)


@router.patch("/{family_id}", summary="Update a family (any subset of fields)")
async def patch_family(family_id: str, payload: FamilyUpdate, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    return await _update(family_id, payload, db, current_user)


@router.post("/{family_id}/members", summary="Add a voter to a family")
async def post_family_member(
    family_id: str, payload: FamilyMemberAdd, db: DbSession, current_user: CanEdit
) -> dict[str, Any]:
    family = await get_family_or_404(db, family_id)
    voter = await find_voter(db, payload.voter_ref())
    await add_member(db, family, voter, payload.relation, actor_id=current_user.id)
    await db.commit()
    family = await get_family_or_404(db, family_id)
    return (await family_rows(db, [family]))[0]


@router.post("/{family_id}/members/batch", summary="Add several voters to a family")
async def post_family_members_batch(
    family_id: str, payload: FamilyMembersBatch, db: DbSession, current_user: CanEdit
) -> dict[str, Any]:
    family = await get_family_or_404(db, family_id)
    for ref in payload.voters:
        voter = await find_voter(db, ref.model_dump())
        await add_member(db, family, voter, payload.relation, actor_id=current_user.id)
    await db.commit()
    family = await get_family_or_404(db, family_id)
    return (await family_rows(db, [family]))[0]


@router.delete("/{family_id}/members/{epic}", summary="Remove a member from a family")
async def delete_family_member(family_id: str, epic: str, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    family = await get_family_or_404(db, family_id)
    voter = (await db.execute(select(Voter).where(Voter.epic_no == epic.strip().upper()))).scalar_one_or_none()
    if voter is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Voter not found")
    await remove_member(db, family, voter, actor_id=current_user.id)
    await db.commit()
    family = await get_family_or_404(db, family_id)
    return (await family_rows(db, [family]))[0]


@router.delete("/{family_id}", summary="Delete a family")
async def delete_family(family_id: str, db: DbSession, current_user: CanDelete) -> dict[str, Any]:
    family = await get_family_or_404(db, family_id)
    await log_activity(
        db,
        actor_id=current_user.id,
        action_type="family_deleted",
        module="families",
        reference_id=family.id,
        description=f"Deleted family {format_id(FAMILY_PREFIX, family.id)} ({family.head_name})",
    )
    await db.delete(family)
    await db.commit()
    return {"success": True}
