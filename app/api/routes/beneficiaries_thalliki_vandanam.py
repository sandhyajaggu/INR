from app.core.beneficiary_scheme_router import build_beneficiary_scheme_router
from app.schemas.beneficiary_schemes import ThallikiVandanamCreate, ThallikiVandanamOut, ThallikiVandanamUpdate

router = build_beneficiary_scheme_router(
    scheme_code="thalliki_vandanam",
    prefix="/beneficiaries/thalliki-vandanam",
    tags=["Beneficiaries - Thalliki Vandanam"],
    create_schema=ThallikiVandanamCreate,
    update_schema=ThallikiVandanamUpdate,
    out_schema=ThallikiVandanamOut,
    resource_label="Thalliki Vandanam beneficiaries",
    name_field="mother_name",
)
