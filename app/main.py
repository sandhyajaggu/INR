from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import (
    achievements,
    auth,
    beneficiaries,
    beneficiaries_aadabidda_nidhi,
    beneficiaries_annadata_sukhibhava,
    beneficiaries_cmrf,
    beneficiaries_deepam_scheme,
    beneficiaries_maha_shakthi,
    beneficiaries_thalliki_vandanam,
    beneficiaries_yuvagalam,
    booths,
    contact,
    dashboard,
    development_works,
    events,
    files,
    gallery,
    janata_darbar,
    local_leaders,
    mp3,
    notes_followups,
    press,
    public,
    reports,
    schemes,
)
from app.api.routes import settings as settings_routes
from app.api.routes import staff, surveys, videos, voters
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    description=(
        "Backend API for INR MLA CRM — constituency management platform for the "
        "109-Kandukur MLA's office (Kandukur, Lingasamudram, Gudluru, Ulavapadu, "
        "Voletivaripalem mandals)."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
app.mount(settings.upload_base_url, StaticFiles(directory=settings.upload_dir), name="uploads")

# --- Auth & files -------------------------------------------------------
app.include_router(auth.router)
app.include_router(files.router)

# --- Core modules -----------------------------------------------------------
# NOTE: each *.extra_router (static sub-paths like /status-summary, /upcoming)
# must be included BEFORE its module's generic CRUD router — the generic
# router's bare "/{item_id}" path param would otherwise swallow those static
# paths and 422 on them before they're ever reached.
app.include_router(voters.router)
app.include_router(booths.router)
app.include_router(development_works.extra_router)
app.include_router(development_works.router)
app.include_router(schemes.router)
# NOTE: each per-scheme beneficiaries router (e.g. /beneficiaries/cmrf) must be
# included BEFORE the generic beneficiaries.router — its bare "/{beneficiary_id}"
# path param would otherwise swallow "/beneficiaries/cmrf" etc. and 422 on them.
app.include_router(beneficiaries_cmrf.router)
app.include_router(beneficiaries_aadabidda_nidhi.router)
app.include_router(beneficiaries_thalliki_vandanam.router)
app.include_router(beneficiaries_deepam_scheme.router)
app.include_router(beneficiaries_maha_shakthi.router)
app.include_router(beneficiaries_annadata_sukhibhava.router)
app.include_router(beneficiaries_yuvagalam.router)
app.include_router(beneficiaries.router)

# --- Multimedia -------------------------------------------------------------
app.include_router(gallery.router)
app.include_router(mp3.extra_router)
app.include_router(mp3.router)
app.include_router(videos.router)
app.include_router(press.router)

# --- Engagement modules -------------------------------------------------------
app.include_router(surveys.router)
app.include_router(events.extra_router)
app.include_router(events.router)
app.include_router(notes_followups.router)
app.include_router(local_leaders.router)
app.include_router(janata_darbar.router)

# --- Public-facing ------------------------------------------------------
app.include_router(contact.router)
app.include_router(public.router)
app.include_router(achievements.router)

# --- Analytics & admin -------------------------------------------------
app.include_router(reports.router)
app.include_router(dashboard.router)
app.include_router(staff.router)
app.include_router(settings_routes.router)


@app.get("/health", tags=["Health"], summary="Health check")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
