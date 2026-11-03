"""Page-level access control, mirroring the frontend's src/config/access.js.

Every staff account has a per-page access map {page_key: level}. The level
decides what the account can do on that page's APIs:

    none     -> no access
    view     -> read
    download -> read + export
    edit     -> read + add / edit / upload / change status
    admin    -> everything, including delete

super_admin accounts always get "admin" on every page.
"""

PAGE_KEYS: list[str] = [
    "dashboard",
    "voters",
    "families",
    "booth_management",
    "development_works",
    "cmrf_applications",
    "government_schemes",
    "beneficiaries",
    "government_offices",
    "public_enquiry",
    "surveys_campaigns",
    "communication",
    "media_gallery",
    "events",
    "reports_analytics",
    "user_management",
    "audit_logs",
    "settings",
]

LEVEL_RANK: dict[str, int] = {"none": 0, "view": 1, "download": 2, "edit": 5, "admin": 7, "full": 7}

# Roles offered in the User Management form (USER_ROLES + "Staff" + "Custom").
USER_ROLES: list[str] = [
    "Super Admin",
    "Admin",
    "Constituency Coordinator",
    "Mandal In-Charge",
    "Booth Agent",
    "Survey Agent",
    "Staff",
    "Custom",
]

ROLE_SCOPE: dict[str, str] = {
    "Super Admin": "All mandals",
    "Admin": "All mandals",
    "Constituency Coordinator": "All mandals",
    "Mandal In-Charge": "Assigned mandal only",
    "Booth Agent": "Assigned booth only",
    "Survey Agent": "Assigned mandal only",
}

_ADMIN_ONLY_PAGES = {"user_management", "audit_logs", "settings"}


def login_role_for(display_role: str) -> str:
    """Map a User Management role label to the login role (super_admin / admin / staff)."""
    if display_role in ("Super Admin", "super_admin"):
        return "super_admin"
    if display_role in ("Admin", "admin"):
        return "admin"
    return "staff"


def display_role_for(login_role: str) -> str:
    return {"super_admin": "Super Admin", "admin": "Admin"}.get(login_role, "Staff")


def default_access(display_role: str) -> dict[str, str]:
    """Same defaults as accessOf() in the frontend."""
    access: dict[str, str] = {}
    for key in PAGE_KEYS:
        if display_role in ("Super Admin", "super_admin"):
            access[key] = "admin"
        elif display_role in ("Admin", "admin"):
            access[key] = "none" if key in _ADMIN_ONLY_PAGES else "edit"
        elif display_role in ("Staff", "staff"):
            access[key] = "view" if key in ("voters", "events", "public_enquiry", "dashboard") else "none"
        elif display_role == "Booth Agent":
            access[key] = "view" if key in ("voters", "booth_management") else "none"
        else:
            access[key] = "none"
    return access


def normalize_access(access: dict[str, str] | None, display_role: str) -> dict[str, str]:
    """Fill in any missing page keys and drop unknown levels."""
    base = default_access(display_role)
    if not access:
        return base
    for key in PAGE_KEYS:
        level = access.get(key)
        if level in LEVEL_RANK:
            base[key] = level
    return base


def page_level(user, page_key: str) -> str:
    if user.role == "super_admin":
        return "admin"
    access = normalize_access(getattr(user, "access", None), getattr(user, "display_role", None) or display_role_for(user.role))
    return access.get(page_key, "none")


def has_access(user, page_key: str, minimum: str) -> bool:
    return LEVEL_RANK.get(page_level(user, page_key), 0) >= LEVEL_RANK[minimum]
