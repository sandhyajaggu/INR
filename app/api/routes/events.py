"""Events page (frontend: EventsTable.js, AddEventModal, EventDetailsDrawer, UploadEventsModal, mockEventsApi).

    GET    /events                 listEvents()   array (q / mandal / status / type filters)
    GET    /events/upcoming        events dated today or later
    GET    /events/summary         cards: total, upcoming, completed, postponed, cancelled
    GET    /events/{id}            one event
    POST   /events                 createEvent(data)
    PUT    /events/{id}            updateEvent(id, data)
    DELETE /events/{id}            deleteEvent(id) -> {"success": true}
    POST   /events/bulk-upload     Event ID, Event Title, Event Type, Date (YYYY-MM-DD), Time (HH:MM),
                                   Venue, Mandal, Village, Status, Live Link

Ids are "EV-<n>". Record shape: id, title, type, date, time, venue,
mandal, village, status, liveMeetingLink, prevMeetingLinks ("a, b"),
prevMeetingLinksList ([{label, url}]), description, chief_guest,
attendance, photo, createdAt, updatedAt.
"""

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import func, or_, select

from app.core.dependencies import DbSession, page_access
from app.core.ids import format_id, parse_id
from app.core.scope import resolve_scope
from app.models.events import Event
from app.models.geography import Mandal, Village
from app.schemas.bulk_import import BulkImportResult, BulkImportRowError, capped_error_detail
from app.schemas.events import EVENT_HEADER_ALIASES, EventForm
from app.services.activity_service import log_activity
from app.services.excel_import_service import parse_upload_rows
from app.services.geography_service import load_geography_maps, name_maps, resolve_geography

router = APIRouter(prefix="/events", tags=["Events"])

CanView = page_access("events", "view")
CanEdit = page_access("events", "edit")
CanDelete = page_access("events", "admin")

PREFIX = "EV"


async def event_rows(db, events: list[Event]) -> list[dict[str, Any]]:
    mandals, villages = await name_maps(db, {e.mandal_id for e in events}, {e.village_id for e in events})
    out = []
    for e in events:
        links = e.prev_meeting_links or []
        out.append(
            {
                "id": format_id(PREFIX, e.id),
                "title": e.event_title,
                "type": e.event_type,
                "date": e.event_date.isoformat() if e.event_date else None,
                "time": e.event_time.strftime("%H:%M") if e.event_time else None,
                "venue": e.venue,
                "mandal": mandals.get(e.mandal_id),
                "village": villages.get(e.village_id),
                "status": e.status,
                "liveMeetingLink": e.live_meeting_link or "",
                "prevMeetingLinks": ", ".join(l.get("url", "") for l in links if l.get("url")),
                "prevMeetingLinksList": links,
                "description": e.description,
                "chief_guest": e.chief_guest,
                "attendance": e.expected_attendance,
                "photo": e.photo_url,
                "createdAt": e.created_at,
                "updatedAt": e.updated_at,
            }
        )
    return out


async def _values(db, form: EventForm) -> dict[str, Any]:
    mandal_id, village_id = await resolve_geography(db, mandal_name=form.mandal, village_name=form.village)
    return {
        "event_title": form.title,
        "event_type": form.type,
        "status": form.status,
        "event_date": form.date,
        "event_time": form.time,
        "venue": form.venue,
        "mandal_id": mandal_id,
        "village_id": village_id,
        "live_meeting_link": form.liveMeetingLink,
        "prev_meeting_links": form.links(),
        "description": form.description,
        "chief_guest": form.chief_guest,
        "expected_attendance": form.attendance,
        "photo_url": form.photo,
    }


async def list_event_rows(db, *, scope=None, q=None, mandal=None, status_filter=None, event_type=None,
                          from_date: date | None = None, limit: int | None = None, ascending=False) -> list[dict[str, Any]]:
    stmt = select(Event).outerjoin(Mandal, Mandal.id == Event.mandal_id).outerjoin(Village, Village.id == Event.village_id)
    if scope is not None:
        stmt = scope.apply(stmt, mandal_col=Event.mandal_id)
    if mandal:
        stmt = stmt.where(func.lower(Mandal.name) == mandal.strip().lower())
    if status_filter:
        stmt = stmt.where(Event.status == status_filter)
    if event_type:
        stmt = stmt.where(Event.event_type == event_type)
    if from_date:
        stmt = stmt.where(Event.event_date >= from_date)
    if q and q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(Event.event_title.ilike(term), Event.venue.ilike(term), Event.event_type.ilike(term),
                Mandal.name.ilike(term), Village.name.ilike(term))
        )
    order = (Event.event_date.asc(), Event.event_time.asc()) if ascending else (Event.event_date.desc(), Event.id.desc())
    stmt = stmt.order_by(*order)
    if limit:
        stmt = stmt.limit(limit)
    return await event_rows(db, list((await db.execute(stmt)).scalars().all()))


async def _get(db, event_id: str) -> Event:
    obj = await db.get(Event, parse_id(event_id, label="Event"), populate_existing=True)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    return obj


@router.get("", summary="List events")
async def list_events(
    db: DbSession,
    current_user: CanView,
    q: str | None = Query(None),
    mandal: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    event_type: str | None = Query(None, alias="type"),
) -> list[dict[str, Any]]:
    return await list_event_rows(
        db, scope=await resolve_scope(db, current_user), q=q, mandal=mandal, status_filter=status_filter, event_type=event_type
    )


@router.get("/upcoming", summary="Events dated today or later (soonest first)")
async def upcoming_events(db: DbSession, current_user: CanView, limit: int = Query(50, ge=1, le=500)) -> list[dict[str, Any]]:
    return await list_event_rows(db, from_date=date.today(), limit=limit, ascending=True)


@router.get("/summary", summary="Events page summary cards")
async def events_summary(db: DbSession, current_user: CanView) -> dict[str, int]:
    stmt = select(Event.status, func.count()).group_by(Event.status)
    stmt = (await resolve_scope(db, current_user)).apply(stmt, mandal_col=Event.mandal_id)
    counts = dict((await db.execute(stmt)).all())
    return {
        "total": sum(counts.values()),
        "upcoming": counts.get("Upcoming", 0) + counts.get("Scheduled", 0),
        "completed": counts.get("Completed", 0),
        "postponed": counts.get("Postponed", 0),
        "cancelled": counts.get("Cancelled", 0),
    }


@router.post("/bulk-upload", response_model=BulkImportResult, summary="Bulk-import events")
async def bulk_upload_events(file: UploadFile, db: DbSession, current_user: CanEdit) -> BulkImportResult:
    rows = await parse_upload_rows(
        file, required_columns={"title", "type", "date", "venue", "mandal"}, aliases=EVENT_HEADER_ALIASES
    )
    errors: list[BulkImportRowError] = []
    mandal_map, village_map, _ = await load_geography_maps(db)
    ready = []
    for raw in rows:
        row_num = raw["_row_number"]
        try:
            form = EventForm.model_validate(raw)
        except ValidationError as exc:
            reason = "; ".join(f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors())
            errors.append(BulkImportRowError(row=row_num, reason=reason))
            continue
        mandal_id = mandal_map.get(form.mandal.lower())
        village_id = village_map.get((mandal_id, form.village.lower())) if mandal_id and form.village else None
        if mandal_id is None or (form.village and village_id is None):
            errors.append(BulkImportRowError(row=row_num, reason=f"Unknown mandal/village '{form.mandal}' / '{form.village}'"))
            continue
        ready.append((form, mandal_id, village_id))
    if errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=capped_error_detail(errors))
    for form, mandal_id, village_id in ready:
        db.add(
            Event(
                event_title=form.title, event_type=form.type, status=form.status, event_date=form.date,
                event_time=form.time, venue=form.venue, mandal_id=mandal_id, village_id=village_id,
                live_meeting_link=form.liveMeetingLink, prev_meeting_links=form.links(), created_by=current_user.id,
            )
        )
    await db.flush()
    await log_activity(
        db, actor_id=current_user.id, action_type="events_bulk_imported", module="events",
        reference_id=None, description=f"Bulk import: {len(ready)} events added",
    )
    await db.commit()
    return BulkImportResult(inserted=len(ready), errors=[])


@router.get("/{event_id}", summary="Get one event")
async def get_event(event_id: str, db: DbSession, current_user: CanView) -> dict[str, Any]:
    return (await event_rows(db, [await _get(db, event_id)]))[0]


@router.post("", status_code=status.HTTP_201_CREATED, summary="Add an event")
async def create_event(payload: EventForm, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    obj = Event(**await _values(db, payload), created_by=current_user.id)
    db.add(obj)
    await db.flush()
    await log_activity(
        db, actor_id=current_user.id, action_type="event_added", module="events", reference_id=obj.id,
        description=f"Added event {obj.event_title} on {obj.event_date}",
    )
    await db.commit()
    return (await event_rows(db, [await _get(db, str(obj.id))]))[0]


@router.put("/{event_id}", summary="Update an event")
async def update_event(event_id: str, payload: EventForm, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    obj = await _get(db, event_id)
    before = (await event_rows(db, [obj]))[0]
    for field, value in (await _values(db, payload)).items():
        setattr(obj, field, value)
    await db.commit()
    after = (await event_rows(db, [await _get(db, event_id)]))[0]
    keys = ("title", "type", "date", "time", "venue", "mandal", "village", "status", "liveMeetingLink", "prevMeetingLinks")
    await log_activity(
        db, actor_id=current_user.id, action_type="event_updated", module="events", reference_id=obj.id,
        description=f"Updated event {after['title']}",
        changes=[[k, str(before[k] or "—"), str(after[k] or "—")] for k in keys if before[k] != after[k]],
        commit=True,
    )
    return after


@router.delete("/{event_id}", summary="Delete an event")
async def delete_event(event_id: str, db: DbSession, current_user: CanDelete) -> dict[str, Any]:
    obj = await _get(db, event_id)
    await log_activity(
        db, actor_id=current_user.id, action_type="event_deleted", module="events", reference_id=obj.id,
        description=f"Deleted event {obj.event_title}",
    )
    await db.delete(obj)
    await db.commit()
    return {"success": True}
