from app.core.crud_router import build_crud_router
from app.models.notes_followups import NoteFollowup
from app.schemas.notes_followups import NoteFollowupCreate, NoteFollowupOut, NoteFollowupUpdate

router = build_crud_router(
    model=NoteFollowup,
    create_schema=NoteFollowupCreate,
    update_schema=NoteFollowupUpdate,
    out_schema=NoteFollowupOut,
    prefix="/notes-followups",
    tags=["Notes & Follow Ups"],
    resource_label="notes & follow-ups",
    search_field="subject",
)
