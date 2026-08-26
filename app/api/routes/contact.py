from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from app.core.dependencies import CurrentUser, DbSession, require_staff
from app.models.contact import ContactMessage
from app.schemas.common import PaginatedResponse
from app.schemas.contact import ContactMessageCreate, ContactMessageOut, ContactMessageStatusUpdate
from app.services.beneficiary_service import link_voter_by_epic
from app.services.geography_service import resolve_geography

router = APIRouter(tags=["Contact Us"])


@router.post(
    "/contact",
    response_model=ContactMessageOut,
    status_code=status.HTTP_201_CREATED,
    summary="Submit the Contact Us form (public, unauthenticated)",
)
async def submit_contact_message(payload: ContactMessageCreate, db: DbSession) -> ContactMessage:
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
    return obj


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
    stmt = select(ContactMessage)
    count_stmt = select(func.count()).select_from(ContactMessage)
    if status_filter:
        stmt = stmt.where(ContactMessage.status == status_filter)
        count_stmt = count_stmt.where(ContactMessage.status == status_filter)

    total = (await db.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(ContactMessage.id.desc()).offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(stmt)).scalars().all()
    return PaginatedResponse(
        items=items, total=total, page=page, page_size=page_size, pages=ceil(total / page_size) if page_size else 0
    )


@router.put(
    "/contact-messages/{message_id}/status",
    response_model=ContactMessageOut,
    summary="Update a contact message's status (staff-only)",
    dependencies=[Depends(require_staff)],
)
async def update_contact_message_status(
    message_id: int, payload: ContactMessageStatusUpdate, db: DbSession
) -> ContactMessage:
    obj = await db.get(ContactMessage, message_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contact message not found")
    obj.status = payload.status
    await db.commit()
    await db.refresh(obj)
    return obj
