from app.core.crud_router import build_crud_router
from app.models.multimedia import Video
from app.schemas.multimedia import VideoCreate, VideoOut, VideoUpdate

router = build_crud_router(
    model=Video,
    create_schema=VideoCreate,
    update_schema=VideoUpdate,
    out_schema=VideoOut,
    prefix="/videos",
    tags=["Multimedia - Videos"],
    resource_label="videos",
    search_field="title",
)
