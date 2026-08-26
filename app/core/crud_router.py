"""Generic CRUD router factory.

Most dashboard modules (Booths, Development Works, Schemes Master, Gallery,
MP3, Videos, Press, Surveys & Feedback, Events, Notes & Follow Ups, Local
Leaders) are a plain paginated list/filter/search + CRUD set over one table.
Rather than hand-write that boilerplate 11 times, this factory builds it once;
modules with real bespoke logic (Voters, Beneficiaries, Staff, Janata Darbar,
Achievements, Contact Us, Reports, Dashboard, Settings) get their own router
in app/api/routes/ instead of using this.
"""

from math import ceil
from typing import Any, Type, TypeVar

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select

from app.core.database import Base
from app.core.dependencies import CurrentUser, DbSession, RequireStaff, RequireSuperAdmin
from app.schemas.common import PaginatedResponse
from app.services.activity_service import log_activity
from app.services.geography_service import resolve_geography

ModelT = TypeVar("ModelT", bound=Base)


async def _resolve_geography_fields(db: DbSession, data: dict[str, Any]) -> None:
    """If the payload carries mandal_name/village_name, resolve them to IDs in-place.

    A no-op for schemas that don't have a mandal_name field at all.
    """
    if "mandal_name" not in data:
        return
    mandal_name = data.pop("mandal_name")
    village_name = data.pop("village_name", None)
    mandal_id, village_id = await resolve_geography(db, mandal_name=mandal_name, village_name=village_name)
    data["mandal_id"] = mandal_id
    data["village_id"] = village_id

# Query params applied only when the target model actually has the column.
GENERIC_FILTER_COLUMNS = ("mandal_id", "village_id", "status", "category")


def build_crud_router(
    *,
    model: Type[ModelT],
    create_schema: Type[BaseModel],
    update_schema: Type[BaseModel],
    out_schema: Type[BaseModel],
    prefix: str,
    tags: list[str],
    resource_label: str,
    search_field: str | None = None,
    activity_module: str | None = None,
    name_field: str = "id",
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=tags)
    singular = resource_label[:-1] if resource_label.endswith("s") else resource_label

    @router.get(
        "",
        response_model=PaginatedResponse[out_schema],
        summary=f"List {resource_label}",
        description=(
            f"Paginated, filterable list of {resource_label}. "
            "Supports mandal_id/village_id/status/category filters where the module has that column, "
            + (f"plus free-text search (`q`) on `{search_field}`." if search_field else "")
        ),
    )
    async def list_items(
        db: DbSession,
        current_user: CurrentUser,
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=200),
        mandal_id: int | None = Query(None),
        village_id: int | None = Query(None),
        status: str | None = Query(None),
        category: str | None = Query(None),
        q: str | None = Query(None, description="Free-text search"),
    ) -> Any:
        stmt = select(model)
        count_stmt = select(func.count()).select_from(model)

        conditions = []
        local_values = {"mandal_id": mandal_id, "village_id": village_id, "status": status, "category": category}
        for column_name in GENERIC_FILTER_COLUMNS:
            value = local_values[column_name]
            if value is not None and hasattr(model, column_name):
                conditions.append(getattr(model, column_name) == value)
        if q and search_field and hasattr(model, search_field):
            conditions.append(getattr(model, search_field).ilike(f"%{q}%"))

        for condition in conditions:
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        total = (await db.execute(count_stmt)).scalar_one()
        stmt = stmt.order_by(model.id.desc()).offset((page - 1) * page_size).limit(page_size)
        items = (await db.execute(stmt)).scalars().all()

        return PaginatedResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=ceil(total / page_size) if page_size else 0,
        )

    @router.get("/{item_id}", response_model=out_schema, summary=f"Get one {singular}")
    async def get_item(item_id: int, db: DbSession, current_user: CurrentUser) -> Any:
        obj = await db.get(model, item_id)
        if obj is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{singular} not found")
        return obj

    @router.post(
        "",
        response_model=out_schema,
        status_code=status.HTTP_201_CREATED,
        summary=f"Create a {singular}",
    )
    async def create_item(
        payload: create_schema, db: DbSession, current_user: RequireStaff  # type: ignore[valid-type]
    ) -> Any:
        data = payload.model_dump()
        await _resolve_geography_fields(db, data)
        obj = model(**data)
        db.add(obj)
        await db.flush()
        if activity_module:
            await log_activity(
                db,
                actor_id=current_user.id,
                action_type=f"{activity_module}_added",
                module=activity_module,
                reference_id=obj.id,
                description=f"{singular.capitalize()} '{getattr(obj, name_field, obj.id)}' added",
            )
        await db.commit()
        await db.refresh(obj)
        return obj

    @router.put(
        "/{item_id}",
        response_model=out_schema,
        summary=f"Update a {singular}",
    )
    async def update_item(
        item_id: int,
        payload: update_schema,  # type: ignore[valid-type]
        db: DbSession,
        current_user: RequireStaff,
    ) -> Any:
        obj = await db.get(model, item_id)
        if obj is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{singular} not found")
        data = payload.model_dump()
        await _resolve_geography_fields(db, data)
        for field, value in data.items():
            setattr(obj, field, value)
        if activity_module:
            await log_activity(
                db,
                actor_id=current_user.id,
                action_type=f"{activity_module}_updated",
                module=activity_module,
                reference_id=obj.id,
                description=f"{singular.capitalize()} '{getattr(obj, name_field, obj.id)}' updated",
            )
        await db.commit()
        await db.refresh(obj)
        return obj

    @router.delete(
        "/{item_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary=f"Delete a {singular} (super_admin only)",
    )
    async def delete_item(
        item_id: int, db: DbSession, current_user: RequireSuperAdmin
    ) -> None:
        obj = await db.get(model, item_id)
        if obj is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{singular} not found")
        if activity_module:
            await log_activity(
                db,
                actor_id=current_user.id,
                action_type=f"{activity_module}_deleted",
                module=activity_module,
                reference_id=item_id,
                description=f"{singular.capitalize()} '{getattr(obj, name_field, obj.id)}' deleted",
            )
        await db.delete(obj)
        await db.commit()

    return router
