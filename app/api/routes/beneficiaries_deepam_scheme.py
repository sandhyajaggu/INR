from app.core.beneficiary_scheme_router import build_beneficiary_scheme_router
from app.schemas.beneficiary_schemes import DeepamSchemeCreate, DeepamSchemeOut, DeepamSchemeUpdate

router = build_beneficiary_scheme_router(
    scheme_code="deepam_scheme",
    prefix="/beneficiaries/deepam-scheme",
    tags=["Beneficiaries - Deepam Scheme"],
    create_schema=DeepamSchemeCreate,
    update_schema=DeepamSchemeUpdate,
    out_schema=DeepamSchemeOut,
    resource_label="Deepam Scheme beneficiaries",
    name_field="head_of_household_name",
)
