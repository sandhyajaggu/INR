from collections.abc import AsyncGenerator, Sequence
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import has_access
from app.core.database import get_db
from app.core.security import decode_token
from app.models.staff import StaffUser

# HTTPBearer (not OAuth2PasswordBearer) — this app uses plain JWT bearer auth,
# not the OAuth2 protocol. OAuth2PasswordBearer makes Swagger UI's "Authorize"
# dialog render a full OAuth2 login form (client_id/secret, username/password)
# that POSTs form-encoded data to tokenUrl expecting an OAuth2 token response —
# but /auth/login takes a JSON body (role/email/password/captcha) and returns
# our own token shape, so that flow can never actually succeed. HTTPBearer
# gives Swagger UI a single "paste your token" field instead, which matches
# what we actually implemented.
bearer_scheme = HTTPBearer(auto_error=False)

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> StaffUser:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise credentials_error

    payload = decode_token(credentials.credentials)
    if payload is None or payload.get("type") != "access":
        raise credentials_error

    staff_id = payload.get("sub")
    if staff_id is None:
        raise credentials_error

    user = await db.get(StaffUser, int(staff_id))
    if user is None or user.status != "active":
        raise credentials_error

    return user


CurrentUser = Annotated[StaffUser, Depends(get_current_user)]


def require_roles(*roles: str):
    """Dependency factory: raises 403 unless the current user's role is in `roles`."""

    async def _checker(current_user: CurrentUser) -> StaffUser:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' is not permitted to perform this action",
            )
        return current_user

    return _checker


def require_page(page_key: str, minimum: str = "view"):
    """Dependency factory: 403 unless the user's access map gives `minimum` (or more) on `page_key`.

    Levels follow the frontend's access matrix: view < download < edit < admin.
    Use "view" for reads, "download" for exports, "edit" for add/edit/upload/
    status changes and "admin" for deletes. super_admin always passes.
    """

    async def _checker(current_user: CurrentUser) -> StaffUser:
        if not has_access(current_user, page_key, minimum):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You do not have '{minimum}' access to {page_key.replace('_', ' ')}",
            )
        return current_user

    return _checker


def page_access(page_key: str, minimum: str = "view"):
    """Annotated alias builder: `current_user: page_access("families", "edit")`."""
    return Annotated[StaffUser, Depends(require_page(page_key, minimum))]


# Any authenticated staff member (super_admin or admin)
require_staff = require_roles("super_admin", "admin")

# DELETE routes: super_admin only — admin gets 403
require_super_admin = require_roles("super_admin")

# Annotated aliases for use as parameter defaults, e.g.
# `current_user: RequireStaff` instead of `current_user: CurrentUser = Depends(require_staff)`
# (FastAPI rejects combining an Annotated-Depends type with a second `= Depends(...)` default).
RequireStaff = Annotated[StaffUser, Depends(require_staff)]
RequireSuperAdmin = Annotated[StaffUser, Depends(require_super_admin)]
