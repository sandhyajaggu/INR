from app.core.beneficiary_scheme_router import build_beneficiary_scheme_router
from app.schemas.beneficiary_schemes import MahaShakthiCreate, MahaShakthiOut, MahaShakthiUpdate

router = build_beneficiary_scheme_router(
    scheme_code="maha_shakthi",
    prefix="/beneficiaries/maha-shakthi",
    tags=["Beneficiaries - Maha Shakthi"],
    create_schema=MahaShakthiCreate,
    update_schema=MahaShakthiUpdate,
    out_schema=MahaShakthiOut,
    resource_label="Maha Shakthi beneficiaries",
    name_field="beneficiary_name",
)
