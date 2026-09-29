"""Booth Summary page endpoints — Super Admin only.

Static paths (/summary, /export) are declared before "/{booth_id}" so the
path param doesn't swallow them.
"""

from datetime import date

from fastapi import APIRouter, Query, Response, status

from app.core.dependencies import DbSession, RequireSuperAdmin
from app.schemas.common import PaginatedResponse
from app.schemas.geography import BoothCreate, BoothOut, BoothSummary, BoothUpdate
from app.services import booth_service

router = APIRouter(prefix="/booths", tags=["Booths"])

StatusFilter = Query(None, alias="status", pattern="^(On Time|Delayed|Pending)$", description="On Time, Delayed or Pending (no status yet)")
MandalFilter = Query(None, description="Mandal name, e.g. Kandukur (All Mandals = leave empty)")
VillageFilter = Query(None, description="Village name within the mandal")
SearchFilter = Query(None, description="Search by Booth No. or In-charge name")


@router.get("", response_model=PaginatedResponse[BoothOut], summary="Booth Summary table (search / filter)")
async def list_booths(
    db: DbSession,
    current_user: RequireSuperAdmin,
    mandal_name: str | None = MandalFilter,
    village_name: str | None = VillageFilter,
    q: str | None = SearchFilter,
    status_filter: str | None = StatusFilter,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
) -> PaginatedResponse[BoothOut]:
    return await booth_service.list_booths(
        db,
        mandal_name=mandal_name,
        village_name=village_name,
        q=q,
        status_filter=status_filter,
        page=page,
        page_size=page_size,
    )


@router.get("/summary", response_model=BoothSummary, summary="Summary cards: Total / Completed / Pending / Delayed")
async def booth_summary(
    db: DbSession,
    current_user: RequireSuperAdmin,
    mandal_name: str | None = MandalFilter,
    village_name: str | None = VillageFilter,
    q: str | None = SearchFilter,
) -> BoothSummary:
    return await booth_service.booth_summary(db, mandal_name=mandal_name, village_name=village_name, q=q)


@router.get(
    "/export",
    summary="Export the (filtered) booth list as CSV",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}}},
)
async def export_booths(
    db: DbSession,
    current_user: RequireSuperAdmin,
    mandal_name: str | None = MandalFilter,
    village_name: str | None = VillageFilter,
    q: str | None = SearchFilter,
    status_filter: str | None = StatusFilter,
) -> Response:
    content = await booth_service.export_booths_csv(
        db, mandal_name=mandal_name, village_name=village_name, q=q, status_filter=status_filter
    )
    filename = f"booths_{date.today().isoformat()}.csv"
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{booth_id}", response_model=BoothOut, summary="Get one booth")
async def get_booth(booth_id: int, db: DbSession, current_user: RequireSuperAdmin) -> BoothOut:
    return await booth_service.get_booth_out(db, booth_id)


@router.post("", response_model=BoothOut, status_code=status.HTTP_201_CREATED, summary="Add a booth")
async def create_booth(payload: BoothCreate, db: DbSession, current_user: RequireSuperAdmin) -> BoothOut:
    return await booth_service.create_booth(db, payload)


@router.put("/{booth_id}", response_model=BoothOut, summary="Update a booth")
async def update_booth(
    booth_id: int, payload: BoothUpdate, db: DbSession, current_user: RequireSuperAdmin
) -> BoothOut:
    return await booth_service.update_booth(db, booth_id, payload)


@router.delete("/{booth_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a booth")
async def delete_booth(booth_id: int, db: DbSession, current_user: RequireSuperAdmin) -> None:
    await booth_service.delete_booth(db, booth_id)
