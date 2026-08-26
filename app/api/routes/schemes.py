from app.core.crud_router import build_crud_router
from app.models.schemes import Scheme
from app.schemas.schemes import SchemeCreate, SchemeOut, SchemeUpdate

router = build_crud_router(
    model=Scheme,
    create_schema=SchemeCreate,
    update_schema=SchemeUpdate,
    out_schema=SchemeOut,
    prefix="/schemes",
    tags=["Schemes (Master)"],
    resource_label="schemes",
    search_field="scheme_name",
)
