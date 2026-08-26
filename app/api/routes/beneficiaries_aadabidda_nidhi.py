from app.core.beneficiary_scheme_router import build_beneficiary_scheme_router
from app.schemas.beneficiary_schemes import AadabiddaNidhiCreate, AadabiddaNidhiOut, AadabiddaNidhiUpdate

router = build_beneficiary_scheme_router(
    scheme_code="aadabidda_nidhi",
    prefix="/beneficiaries/aadabidda-nidhi",
    tags=["Beneficiaries - Aadabidda Nidhi"],
    create_schema=AadabiddaNidhiCreate,
    update_schema=AadabiddaNidhiUpdate,
    out_schema=AadabiddaNidhiOut,
    resource_label="Aadabidda Nidhi beneficiaries",
    name_field="beneficiary_name",
)
