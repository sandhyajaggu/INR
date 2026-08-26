"""Bespoke because token_number is auto-generated server-side on create."""

from math import ceil

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.core.dependencies import CurrentUser, DbSession, RequireStaff, RequireSuperAdmin
from app.models.janata_darbar import JanataDarbarVisit
from app.schemas.common import PaginatedResponse
from app.schemas.janata_darbar import JanataDarbarCreate, JanataDarbarOut, JanataDarbarUpdate
from app.services.beneficiary_service import link_voter_by_epic
from app.services.geography_service import resolve_geography

router = APIRouter(prefix="/janata-darbar", tags=["Janata Darbar"])


@router.get("", response_model=PaginatedResponse[JanataDarbarOut], summary="List Janata Darbar visits")
async def list_visits(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    mandal_id: int | None = Query(None),
    village_id: int | None = Query(None),
    status: str | None = Query(None),
) -> PaginatedResponse[JanataDarbarOut]:
    stmt = select(JanataDarbarVisit)
    count_stmt = select(func.count()).select_from(JanataDarbarVisit)
    conditions = []
    if mandal_id is not None:
        conditions.append(JanataDarbarVisit.mandal_id == mandal_id)
    if village_id is not None:
        conditions.append(JanataDarbarVisit.village_id == village_id)
    if status:
        conditions.append(JanataDarbarVisit.status == status)
    for condition in conditions:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = (await db.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(JanataDarbarVisit.id.desc()).offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(stmt)).scalars().all()
    return PaginatedResponse(
        items=items, total=total, page=page, page_size=page_size, pages=ceil(total / page_size) if page_size else 0
    )


@router.get("/{visit_id}", response_model=JanataDarbarOut, summary="Get one visit")
async def get_visit(visit_id: int, db: DbSession, current_user: CurrentUser) -> JanataDarbarVisit:
    obj = await db.get(JanataDarbarVisit, visit_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Visit not found")
    return obj


@router.post(
    "",
    response_model=JanataDarbarOut,
    status_code=status.HTTP_201_CREATED,
    summary="Log a Janata Darbar visit (token_number auto-generated)",
)
async def create_visit(
    payload: JanataDarbarCreate, db: DbSession, current_user: RequireStaff
) -> JanataDarbarVisit:
    data = payload.model_dump()
    if data.get("epic_no"):
        data["epic_no"] = data["epic_no"].upper()
    data["voter_id"] = await link_voter_by_epic(db, data.get("epic_no"))
    mandal_name = data.pop("mandal_name", None)
    village_name = data.pop("village_name", None)
    data["mandal_id"], data["village_id"] = await resolve_geography(
        db, mandal_name=mandal_name, village_name=village_name
    )

    obj = JanataDarbarVisit(**data, token_number="PENDING")
    db.add(obj)
    await db.flush()  # assigns obj.id

    obj.token_number = f"JD{obj.id:06d}"
    await db.commit()
    await db.refresh(obj)
    return obj


@router.put("/{visit_id}", response_model=JanataDarbarOut, summary="Update a visit")
async def update_visit(
    visit_id: int, payload: JanataDarbarUpdate, db: DbSession, current_user: RequireStaff
) -> JanataDarbarVisit:
    obj = await db.get(JanataDarbarVisit, visit_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Visit not found")
    data = payload.model_dump()
    if data.get("epic_no"):
        data["epic_no"] = data["epic_no"].upper()
    data["voter_id"] = await link_voter_by_epic(db, data.get("epic_no"))
    mandal_name = data.pop("mandal_name", None)
    village_name = data.pop("village_name", None)
    data["mandal_id"], data["village_id"] = await resolve_geography(
        db, mandal_name=mandal_name, village_name=village_name
    )
    for field, value in data.items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete(
    "/{visit_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a visit (super_admin only)"
)
async def delete_visit(
    visit_id: int, db: DbSession, current_user: RequireSuperAdmin
) -> None:
    obj = await db.get(JanataDarbarVisit, visit_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Visit not found")
    await db.delete(obj)
    await db.commit()
