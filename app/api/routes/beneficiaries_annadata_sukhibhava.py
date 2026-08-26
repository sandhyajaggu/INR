from app.core.beneficiary_scheme_router import build_beneficiary_scheme_router
from app.schemas.beneficiary_schemes import (
    AnnadataSukhibhavaCreate,
    AnnadataSukhibhavaOut,
    AnnadataSukhibhavaUpdate,
)

router = build_beneficiary_scheme_router(
    scheme_code="annadata_sukhibhava",
    prefix="/beneficiaries/annadata-sukhibhava",
    tags=["Beneficiaries - Annadata Sukhibhava"],
    create_schema=AnnadataSukhibhavaCreate,
    update_schema=AnnadataSukhibhavaUpdate,
    out_schema=AnnadataSukhibhavaOut,
    resource_label="Annadata Sukhibhava beneficiaries",
    name_field="farmer_name",
)
