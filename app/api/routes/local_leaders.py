"""Bespoke (not generic-factory) because local_leaders stores Aadhaar, which
must be encrypted at rest and masked on every response per the spec.
"""

from math import ceil

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.core.dependencies import CurrentUser, DbSession, RequireStaff, RequireSuperAdmin
from app.models.local_leaders import LocalLeader
from app.schemas.common import PaginatedResponse
from app.schemas.local_leaders import LocalLeaderCreate, LocalLeaderOut, LocalLeaderUpdate
from app.services.encryption_service import encrypt_aadhaar, mask_aadhaar
from app.services.geography_service import resolve_geography

router = APIRouter(prefix="/local-leaders", tags=["Local Leaders"])


def _to_out(obj: LocalLeader) -> LocalLeaderOut:
    return LocalLeaderOut(
        id=obj.id,
        leader_name=obj.leader_name,
        alias_name=obj.alias_name,
        position=obj.position,
        party=obj.party,
        voter_id=obj.voter_id,
        epic_no=obj.epic_no,
        aadhaar_masked=mask_aadhaar(obj.aadhaar_number),
        mobile_number=obj.mobile_number,
        village_id=obj.village_id,
        mandal_id=obj.mandal_id,
        date_joined=obj.date_joined,
        status=obj.status,
        photo_url=obj.photo_url,
        remarks=obj.remarks,
    )


@router.get("", response_model=PaginatedResponse[LocalLeaderOut], summary="List local leaders")
async def list_local_leaders(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    mandal_id: int | None = Query(None),
    village_id: int | None = Query(None),
    party: str | None = Query(None),
    q: str | None = Query(None, description="Search leader_name"),
) -> PaginatedResponse[LocalLeaderOut]:
    stmt = select(LocalLeader)
    count_stmt = select(func.count()).select_from(LocalLeader)
    conditions = []
    if mandal_id is not None:
        conditions.append(LocalLeader.mandal_id == mandal_id)
    if village_id is not None:
        conditions.append(LocalLeader.village_id == village_id)
    if party:
        conditions.append(LocalLeader.party == party)
    if q:
        conditions.append(LocalLeader.leader_name.ilike(f"%{q}%"))
    for condition in conditions:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = (await db.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(LocalLeader.id.desc()).offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(stmt)).scalars().all()
    return PaginatedResponse(
        items=[_to_out(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=ceil(total / page_size) if page_size else 0,
    )


@router.get("/{leader_id}", response_model=LocalLeaderOut, summary="Get one local leader")
async def get_local_leader(leader_id: int, db: DbSession, current_user: CurrentUser) -> LocalLeaderOut:
    obj = await db.get(LocalLeader, leader_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Local leader not found")
    return _to_out(obj)


@router.post(
    "", response_model=LocalLeaderOut, status_code=status.HTTP_201_CREATED, summary="Add a local leader"
)
async def create_local_leader(
    payload: LocalLeaderCreate, db: DbSession, current_user: RequireStaff
) -> LocalLeaderOut:
    data = payload.model_dump()
    mandal_name = data.pop("mandal_name")
    village_name = data.pop("village_name")
    data["mandal_id"], data["village_id"] = await resolve_geography(
        db, mandal_name=mandal_name, village_name=village_name
    )
    if data.get("aadhaar_number"):
        data["aadhaar_number"] = encrypt_aadhaar(data["aadhaar_number"])
    obj = LocalLeader(**data)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return _to_out(obj)


@router.put("/{leader_id}", response_model=LocalLeaderOut, summary="Update a local leader")
async def update_local_leader(
    leader_id: int,
    payload: LocalLeaderUpdate,
    db: DbSession,
    current_user: RequireStaff,
) -> LocalLeaderOut:
    obj = await db.get(LocalLeader, leader_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Local leader not found")
    data = payload.model_dump()
    mandal_name = data.pop("mandal_name")
    village_name = data.pop("village_name")
    data["mandal_id"], data["village_id"] = await resolve_geography(
        db, mandal_name=mandal_name, village_name=village_name
    )
    if data.get("aadhaar_number"):
        data["aadhaar_number"] = encrypt_aadhaar(data["aadhaar_number"])
    for field, value in data.items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    return _to_out(obj)


@router.delete(
    "/{leader_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a local leader (super_admin only)",
)
async def delete_local_leader(
    leader_id: int, db: DbSession, current_user: RequireSuperAdmin
) -> None:
    obj = await db.get(LocalLeader, leader_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Local leader not found")
    await db.delete(obj)
    await db.commit()


@router.get(
    "/{leader_id}/aadhaar/reveal",
    summary="Reveal a local leader's plaintext Aadhaar (super_admin only)",
)
async def reveal_local_leader_aadhaar(
    leader_id: int, db: DbSession, current_user: RequireSuperAdmin
) -> dict[str, str | None]:
    from app.services.encryption_service import decrypt_aadhaar

    obj = await db.get(LocalLeader, leader_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Local leader not found")
    return {"aadhaar_number": decrypt_aadhaar(obj.aadhaar_number) if obj.aadhaar_number else None}
