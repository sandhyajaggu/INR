from app.core.beneficiary_scheme_router import build_beneficiary_scheme_router
from app.schemas.beneficiary_schemes import YuvagalamCreate, YuvagalamOut, YuvagalamUpdate

router = build_beneficiary_scheme_router(
    scheme_code="yuvagalam",
    prefix="/beneficiaries/yuvagalam",
    tags=["Beneficiaries - Yuvagalam"],
    create_schema=YuvagalamCreate,
    update_schema=YuvagalamUpdate,
    out_schema=YuvagalamOut,
    resource_label="Yuvagalam beneficiaries",
    name_field="beneficiary_name",
)
