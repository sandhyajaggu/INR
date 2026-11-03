"""User Management (frontend: SuperAdminUserManagement.jsx, mockUserApi).

    GET    /staff                        -> listUsers()
    GET    /staff/{id}                   -> one user
    POST   /staff                        -> addUser()      (returns temporaryPassword once)
    PUT    /staff/{id}                   -> updateUser()
    DELETE /staff/{id}                   -> deleteUser()   ({"success": true})
    POST   /staff/{id}/reset-password    -> resetPassword() ({"temporaryPassword": ...})

IDs are returned as "U-<n>"; path params accept "U-101" or "101".
Access is controlled by the user_management page level.
"""

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.core.access import ROLE_SCOPE, login_role_for, normalize_access
from app.core.dependencies import DbSession, page_access
from app.core.ids import parse_id
from app.core.security import hash_password
from app.models.staff import StaffUser
from app.schemas.staff import (
    ResetPasswordOut,
    SuccessOut,
    UserCreate,
    UserCreatedOut,
    UserOut,
    UserUpdate,
)
from app.services.activity_service import client_ip, diff_changes, log_activity
from app.services.user_service import generate_temporary_password, serialize_user

router = APIRouter(prefix="/staff", tags=["User Management"])

CanView = page_access("user_management", "view")
CanEdit = page_access("user_management", "edit")
CanDelete = page_access("user_management", "admin")


async def _get_user(db: DbSession, user_id: str) -> StaffUser:
    obj = await db.get(StaffUser, parse_id(user_id, label="User record"))
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User record not found")
    return obj


def _guard_super_admin_role(current_user: StaffUser, role: str, target: StaffUser | None = None) -> None:
    """Only a super admin may create, promote to, or edit a Super Admin account."""
    touches_super = role == "Super Admin" or (target is not None and target.role == "super_admin")
    if touches_super and current_user.role != "super_admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a Super Admin can manage Super Admin accounts")


async def _ensure_unique(db: DbSession, *, email: str | None, mobile: str, exclude_id: int | None = None) -> None:
    conditions = [StaffUser.mobile == mobile]
    if email:
        conditions.append(func.lower(StaffUser.email) == email.lower())
    stmt = select(StaffUser).where(or_(*conditions))
    if exclude_id is not None:
        stmt = stmt.where(StaffUser.id != exclude_id)
    clash = (await db.execute(stmt)).scalars().first()
    if clash is not None:
        field = "email" if email and clash.email and clash.email.lower() == email.lower() else "mobile"
        raise HTTPException(status.HTTP_409_CONFLICT, f"A user with this {field} already exists")


def _apply(obj: StaffUser, data: dict) -> None:
    role = data["role"]
    obj.name = data["name"].strip()
    obj.epic_no = data.get("epic")
    obj.mobile = data["mobile"]
    obj.email = data.get("email")
    obj.mandal = data["mandal"]
    obj.village = data["village"]
    obj.address = data["address"].strip()
    obj.photo_url = data.get("photo")
    obj.display_role = role
    obj.role = login_role_for(role)
    obj.scope = data.get("scope") or ROLE_SCOPE.get(role, "All mandals")
    obj.access = normalize_access(data.get("access"), role)
    obj.status = "active" if data.get("status", "Active") == "Active" else "inactive"


@router.get("", response_model=list[UserOut], summary="List all users")
async def list_users(db: DbSession, current_user: CanView) -> list[dict]:
    users = (await db.execute(select(StaffUser).order_by(StaffUser.id.desc()))).scalars().all()
    return [serialize_user(u) for u in users]


@router.get("/{user_id}", response_model=UserOut, summary="Get one user")
async def get_user(user_id: str, db: DbSession, current_user: CanView) -> dict:
    return serialize_user(await _get_user(db, user_id))


@router.post(
    "",
    response_model=UserCreatedOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a user (returns a one-time temporary password)",
)
async def add_user(payload: UserCreate, request: Request, db: DbSession, current_user: CanEdit) -> dict:
    data = payload.model_dump()
    _guard_super_admin_role(current_user, data["role"])
    await _ensure_unique(db, email=data.get("email"), mobile=data["mobile"])

    temporary_password = generate_temporary_password()
    obj = StaffUser(password_hash=hash_password(temporary_password), must_change_password=True)
    _apply(obj, data)
    db.add(obj)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists") from exc
    await log_activity(
        db,
        actor_id=current_user.id,
        action_type="user_added",
        module="User Management",
        reference_id=obj.id,
        description=f"Added user {obj.name} ({obj.display_role})",
        ip_address=client_ip(request),
    )
    await db.commit()
    await db.refresh(obj)
    return {**serialize_user(obj), "temporaryPassword": temporary_password}


@router.put("/{user_id}", response_model=UserOut, summary="Update a user")
async def update_user(
    user_id: str, payload: UserUpdate, request: Request, db: DbSession, current_user: CanEdit
) -> dict:
    obj = await _get_user(db, user_id)
    data = payload.model_dump()
    _guard_super_admin_role(current_user, data["role"], obj)
    if obj.id == current_user.id and data.get("status") == "Inactive":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot deactivate your own account")
    await _ensure_unique(db, email=data.get("email"), mobile=data["mobile"], exclude_id=obj.id)

    before = serialize_user(obj)
    _apply(obj, data)
    after = serialize_user(obj)
    before.pop("access"), after.pop("access")
    await log_activity(
        db,
        actor_id=current_user.id,
        action_type="user_updated",
        module="User Management",
        reference_id=obj.id,
        description=f"Updated user {obj.name}",
        changes=diff_changes(before, after),
        ip_address=client_ip(request),
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists") from exc
    await db.refresh(obj)
    return serialize_user(obj)


@router.delete("/{user_id}", response_model=SuccessOut, summary="Delete a user")
async def delete_user(user_id: str, request: Request, db: DbSession, current_user: CanDelete) -> dict:
    obj = await _get_user(db, user_id)
    if obj.id == current_user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot delete your own account")
    _guard_super_admin_role(current_user, obj.display_role or "", obj)
    await log_activity(
        db,
        actor_id=current_user.id,
        action_type="user_deleted",
        module="User Management",
        reference_id=obj.id,
        description=f"Deleted user {obj.name}",
        ip_address=client_ip(request),
    )
    await db.delete(obj)
    await db.commit()
    return {"success": True}


@router.post(
    "/{user_id}/reset-password",
    response_model=ResetPasswordOut,
    summary="Reset a user's password to a new temporary password",
)
async def reset_password(user_id: str, request: Request, db: DbSession, current_user: CanEdit) -> dict:
    obj = await _get_user(db, user_id)
    _guard_super_admin_role(current_user, obj.display_role or "", obj)
    temporary_password = generate_temporary_password()
    obj.password_hash = hash_password(temporary_password)
    obj.must_change_password = True
    await log_activity(
        db,
        actor_id=current_user.id,
        action_type="user_password_reset",
        module="User Management",
        reference_id=obj.id,
        description=f"Reset password for {obj.name}",
        ip_address=client_ip(request),
    )
    await db.commit()
    return {"temporaryPassword": temporary_password}
