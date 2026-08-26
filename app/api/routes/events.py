from datetime import date

from fastapi import APIRouter
from sqlalchemy import select

from app.core.crud_router import build_crud_router
from app.core.dependencies import CurrentUser, DbSession
from app.models.events import Event
from app.schemas.events import EventCreate, EventOut, EventUpdate

router = build_crud_router(
    model=Event,
    create_schema=EventCreate,
    update_schema=EventUpdate,
    out_schema=EventOut,
    prefix="/events",
    tags=["Events"],
    resource_label="events",
    search_field="event_title",
)

extra_router = APIRouter(prefix="/events", tags=["Events"])


@extra_router.get("/upcoming", response_model=list[EventOut], summary="Upcoming events (event_date >= today)")
async def upcoming_events(db: DbSession, current_user: CurrentUser) -> list[Event]:
    stmt = select(Event).where(Event.event_date >= date.today()).order_by(Event.event_date.asc())
    return list((await db.execute(stmt)).scalars().all())


# NOTE: main.py must include extra_router BEFORE router — otherwise the
# generic "/{item_id}" route (a bare, un-typed path param) would swallow
# "/events/upcoming" and 422 on it instead of matching this.
