from app.core.crud_router import build_crud_router
from app.models.multimedia import PressGalleryItem
from app.schemas.multimedia import PressGalleryCreate, PressGalleryOut, PressGalleryUpdate

router = build_crud_router(
    model=PressGalleryItem,
    create_schema=PressGalleryCreate,
    update_schema=PressGalleryUpdate,
    out_schema=PressGalleryOut,
    prefix="/press",
    tags=["Multimedia - Press"],
    resource_label="press items",
    search_field="title",
)
