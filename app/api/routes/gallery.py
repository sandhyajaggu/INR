from app.core.crud_router import build_crud_router
from app.models.multimedia import GalleryPhoto
from app.schemas.multimedia import GalleryPhotoCreate, GalleryPhotoOut, GalleryPhotoUpdate

router = build_crud_router(
    model=GalleryPhoto,
    create_schema=GalleryPhotoCreate,
    update_schema=GalleryPhotoUpdate,
    out_schema=GalleryPhotoOut,
    prefix="/gallery",
    tags=["Multimedia - Gallery"],
    resource_label="gallery photos",
    search_field="title",
)
