from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.development_works import DevelopmentWork
from app.schemas.bulk_import import BulkImportResult, BulkImportRowError
from app.schemas.development_works import DevelopmentWorkCreate
from app.services.activity_service import log_activity
from app.services.geography_service import load_geography_maps


async def bulk_import_development_works(
    db: AsyncSession, rows: list[dict], actor_id: int
) -> BulkImportResult:
    """All-or-nothing bulk import of development works from a parsed Excel sheet.

    Development works have no natural uniqueness key (unlike voters' epic_no),
    so there's no duplicate-row rejection here — only per-row field validation
    (via the same DevelopmentWorkCreate schema the manual "Add" form uses) and
    mandal_name/village_name resolution. If any row fails, nothing is written.
    """
    errors: list[BulkImportRowError] = []
    parsed_rows: list[tuple[int, DevelopmentWorkCreate]] = []

    for raw in rows:
        row_num = raw.get("_row_number")
        try:
            parsed_rows.append((row_num, DevelopmentWorkCreate.model_validate(raw)))
        except ValidationError as exc:
            reason = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
            errors.append(BulkImportRowError(row=row_num, reason=reason))

    mandal_map, village_map, _ = await load_geography_maps(db)
    resolved: list[tuple[DevelopmentWorkCreate, int, int | None]] = []
    for row_num, parsed in parsed_rows:
        mandal_id = mandal_map.get(parsed.mandal_name.strip().lower())
        if mandal_id is None:
            errors.append(BulkImportRowError(row=row_num, reason=f"Unknown mandal_name '{parsed.mandal_name}'"))
            continue
        village_id = None
        if parsed.village_name:
            village_id = village_map.get((mandal_id, parsed.village_name.strip().lower()))
            if village_id is None:
                errors.append(
                    BulkImportRowError(
                        row=row_num,
                        reason=f"Unknown village_name '{parsed.village_name}' in mandal '{parsed.mandal_name}'",
                    )
                )
                continue
        resolved.append((parsed, mandal_id, village_id))

    if errors:
        return BulkImportResult(inserted=0, errors=errors)

    works = []
    for parsed, mandal_id, village_id in resolved:
        data = parsed.model_dump(exclude={"mandal_name", "village_name"})
        works.append(DevelopmentWork(**data, mandal_id=mandal_id, village_id=village_id, created_by=actor_id))

    db.add_all(works)
    await db.flush()
    await log_activity(
        db,
        actor_id=actor_id,
        action_type="development_works_bulk_imported",
        module="development_works",
        reference_id=None,
        description=f"Bulk import: {len(works)} development works added",
    )
    await db.commit()
    return BulkImportResult(inserted=len(works), errors=[])
