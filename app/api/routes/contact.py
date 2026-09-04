from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from app.core.dependencies import CurrentUser, DbSession, require_staff
from app.models.contact import ContactMessage
from app.models.geography import Mandal, Village
from app.schemas.common import PaginatedResponse
from app.schemas.contact import ContactMessageCreate, ContactMessageOut, ContactMessageStatusUpdate
from app.services.beneficiary_service import link_voter_by_epic
from app.services.geography_service import resolve_geography

router = APIRouter(tags=["Contact Us"])


def _to_out(obj: ContactMessage, village_name: str | None, mandal_name: str | None) -> ContactMessageOut:
    return ContactMessageOut(
        id=obj.id,
        voter_id=obj.voter_id,
        epic_no=obj.epic_no,
        name=obj.name,
        mobile_number=obj.mobile_number,
        village_id=obj.village_id,
        village_name=village_name,
        mandal_id=obj.mandal_id,
        mandal_name=mandal_name,
        message=obj.message,
        status=obj.status,
        created_at=obj.created_at,
    )


async def _names_for(db: DbSession, mandal_id: int | None, village_id: int | None) -> tuple[str | None, str | None]:
    mandal_name = (
        (await db.execute(select(Mandal.name).where(Mandal.id == mandal_id))).scalar_one_or_none()
        if mandal_id is not None
        else None
    )
    village_name = (
        (await db.execute(select(Village.name).where(Village.id == village_id))).scalar_one_or_none()
        if village_id is not None
        else None
    )
    return mandal_name, village_name


@router.post(
    "/contact",
    response_model=ContactMessageOut,
    status_code=status.HTTP_201_CREATED,
    summary="Submit the Contact Us form (public, unauthenticated)",
)
async def submit_contact_message(payload: ContactMessageCreate, db: DbSession) -> ContactMessageOut:
    data = payload.model_dump()
    if data.get("epic_no"):
        data["epic_no"] = data["epic_no"].upper()
    data["voter_id"] = await link_voter_by_epic(db, data.get("epic_no"))
    mandal_name = data.pop("mandal_name", None)
    village_name = data.pop("village_name", None)
    data["mandal_id"], data["village_id"] = await resolve_geography(
        db, mandal_name=mandal_name, village_name=village_name
    )

    obj = ContactMessage(**data)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    mandal_name, village_name = await _names_for(db, obj.mandal_id, obj.village_id)
    return _to_out(obj, village_name, mandal_name)


@router.get(
    "/contact-messages",
    response_model=PaginatedResponse[ContactMessageOut],
    summary="List contact messages (staff-only)",
    dependencies=[Depends(require_staff)],
)
async def list_contact_messages(
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status_filter: str | None = Query(None, alias="status"),
) -> PaginatedResponse[ContactMessageOut]:
    stmt = (
        select(ContactMessage, Village.name, Mandal.name)
        .outerjoin(Village, Village.id == ContactMessage.village_id)
        .outerjoin(Mandal, Mandal.id == ContactMessage.mandal_id)
    )
    count_stmt = select(func.count()).select_from(ContactMessage)
    if status_filter:
        stmt = stmt.where(ContactMessage.status == status_filter)
        count_stmt = count_stmt.where(ContactMessage.status == status_filter)

    total = (await db.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(ContactMessage.id.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(stmt)).all()
    return PaginatedResponse(
        items=[_to_out(obj, village_name, mandal_name) for obj, village_name, mandal_name in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=ceil(total / page_size) if page_size else 0,
    )


@router.put(
    "/contact-messages/{message_id}/status",
    response_model=ContactMessageOut,
    summary="Update a contact message's status (staff-only)",
    dependencies=[Depends(require_staff)],
)
async def update_contact_message_status(
    message_id: int, payload: ContactMessageStatusUpdate, db: DbSession
) -> ContactMessageOut:
    obj = await db.get(ContactMessage, message_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contact message not found")
    obj.status = payload.status
    await db.commit()
    await db.refresh(obj)
    mandal_name, village_name = await _names_for(db, obj.mandal_id, obj.village_id)
    return _to_out(obj, village_name, mandal_name)
