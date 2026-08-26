from app.core.crud_router import build_crud_router
from app.models.geography import Booth
from app.schemas.geography import BoothCreate, BoothOut, BoothUpdate

router = build_crud_router(
    model=Booth,
    create_schema=BoothCreate,
    update_schema=BoothUpdate,
    out_schema=BoothOut,
    prefix="/booths",
    tags=["Booths"],
    resource_label="booths",
    search_field="booth_name",
)
