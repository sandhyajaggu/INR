"""User Management helpers: response shaping and temporary passwords."""

import secrets
import string

from app.core.access import display_role_for, normalize_access
from app.core.ids import format_id
from app.models.staff import StaffUser

USER_ID_PREFIX = "U"


def generate_temporary_password() -> str:
    """A one-time password shown once to the admin, e.g. 'Inr@4821kqtz'."""
    digits = "".join(secrets.choice(string.digits) for _ in range(4))
    letters = "".join(secrets.choice(string.ascii_lowercase) for _ in range(4))
    return f"Inr@{digits}{letters}"


def user_display_role(user: StaffUser) -> str:
    return user.display_role or display_role_for(user.role)


def serialize_user(user: StaffUser) -> dict:
    role = user_display_role(user)
    return {
        "id": format_id(USER_ID_PREFIX, user.id),
        "name": user.name,
        "epic": user.epic_no,
        "role": role,
        "mobile": user.mobile,
        "email": user.email,
        "mandal": user.mandal,
        "village": user.village,
        "address": user.address,
        "photo": user.photo_url,
        "scope": user.scope or "All mandals",
        "access": normalize_access(user.access, role),
        "status": "Active" if user.status == "active" else "Inactive",
        "lastLoginAt": int(user.last_login_at.timestamp() * 1000) if user.last_login_at else None,
        "mustChangePassword": user.must_change_password,
        "login": "Waiting for first sign-in" if user.must_change_password else "Own password set",
    }


def serialize_session_user(user: StaffUser) -> dict:
    """The `user` object returned by /auth/login and /auth/me (what the frontend stores as currentUser)."""
    data = serialize_user(user)
    data["role"] = user.role  # super_admin / admin / staff (the frontend's adminRole)
    data["displayRole"] = user_display_role(user)
    data["name_te"] = None
    return data
