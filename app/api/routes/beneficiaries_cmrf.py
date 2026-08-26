from app.core.beneficiary_scheme_router import build_beneficiary_scheme_router
from app.schemas.beneficiary_schemes import CmrfCreate, CmrfOut, CmrfUpdate

router = build_beneficiary_scheme_router(
    scheme_code="cmrf",
    prefix="/beneficiaries/cmrf",
    tags=["Beneficiaries - CM Relief Fund"],
    create_schema=CmrfCreate,
    update_schema=CmrfUpdate,
    out_schema=CmrfOut,
    resource_label="CMRF beneficiaries",
    name_field="beneficiary_name",
)
