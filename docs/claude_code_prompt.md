# Build the backend for INR MLA CRM (FastAPI + PostgreSQL)

## Context

I'm building the backend for **INR MLA CRM**, a political constituency management
platform for an MLA's office (109-Kandukur constituency: Kandukur, Lingasamudram,
Gudluru, Ulavapadu, Voletivaripalem mandals). There's an existing React frontend
already live at https://mlainr.com/ that this backend must serve — I'll wire up
the API base URL on my end, you don't need to touch the frontend.

I'm attaching three files — read all of them before writing any code:

1. `INR_MLA_CRM_Project_Documentation.docx` — full functional spec: every page,
   every dashboard module, every table's columns, and every Add/Edit form's
   fields, exactly as the frontend already implements them.
2. `schema.sql` — the PostgreSQL schema I've already designed for this (18
   tables + 5 reporting views). Use this schema as-is; don't redesign it.
   If you think something needs to change, tell me why before changing it.
3. `seed_geography.sql` — INSERT statements for all 5 mandals and every
   village in the constituency. Run this once during initial setup.

## Tech stack (non-negotiable — matches my other backend on this same stack)

- Python 3.11+, **FastAPI**
- **PostgreSQL** with **SQLAlchemy** (async) as the ORM
- **Alembic** for migrations — generate the initial migration from `schema.sql`,
  don't hand-write raw SQL migrations
- **Pydantic v2** for request/response schemas
- **Uvicorn** as the ASGI server
- **JWT** (access + refresh token) for authentication
- **Passlib/bcrypt** for password hashing
- Environment-based config (`.env` / `pydantic-settings`) — no hardcoded secrets
  or connection strings anywhere

## Project structure

Set up a clean, layered FastAPI project — routers / services / models / schemas
separated, not everything in one `main.py`. Use dependency injection for the DB
session and for the current-user/role check. Follow standard FastAPI project
conventions (e.g. `app/api/routes/`, `app/models/`, `app/schemas/`, `app/services/`,
`app/core/`, `alembic/`).

## Authentication & roles

- Single `/auth/login` endpoint. Request includes a `role` field (`super_admin`
  or `admin`), `email`, `password`, and a math CAPTCHA answer (see below).
- A `/auth/captcha` endpoint that returns a simple math challenge (e.g. "7 + 4")
  with a short-lived signed token; login must submit the token + the answer,
  verified server-side.
- `/auth/refresh` and `/auth/forgot-password` (forgot-password can just be a
  stub that returns a reset token for now — I'll wire up email later).
- Role-based access control at the route level:
  - **super_admin**: full CRUD on every module, including DELETE.
  - **admin**: full CRUD on every module **except DELETE** — every DELETE
    route must reject the `admin` role with a 403.
- Voters are NOT authenticated users — there is no voter login. The public
  site only ever reads/writes voter data via the Contact Us form and the
  Beneficiary Lookup, both unauthenticated public endpoints.

## Core modules to build (CRUD + list/filter/search unless noted)

Build a full router for each of these, backed by the matching table(s) in
`schema.sql`. For every listing endpoint, support pagination, and filtering by
`mandal_id` and `village_id` at minimum (most tables carry both). Match the
Add/Edit form fields from the documentation exactly — don't drop or rename
fields.

1. **Voters** — CRUD, search by `epic_no` (exact) and by name (fuzzy,
   `pg_trgm`), filter by mandal/village/booth/gender. Include a
   `GET /voters/summary/by-mandal` endpoint backed by the
   `v_mandal_voter_summary` view, and `GET /voters/gender-distribution` backed
   by `v_voter_gender_distribution`.
2. **Booths** — CRUD, filter by mandal/village.
3. **Development Works** — CRUD, filter by status/mandal, plus a
   `GET /development-works/status-summary` endpoint (`v_development_status_summary`).
4. **Schemes** (master list) — CRUD.
5. **Beneficiaries** — this is the important one. One shared endpoint set
   (`/beneficiaries`) that takes a `scheme_id` (or `scheme_code`) and handles
   all 8 schemes (CMRF, Aadabidda Nidhi, Thalliki Vandanam, Deepam, Maha
   Shakthi, Annadata Sukhibhava, Yuvagalam, plus future ones) through the one
   `beneficiaries` table. Scheme-specific fields go in the `scheme_details`
   JSONB column — validate its shape per `scheme_code` using a Pydantic
   discriminated union or per-scheme sub-schema, so the API still rejects
   malformed scheme-specific data even though the column is JSONB. Also
   build:
   - `GET /beneficiaries/lookup/{epic_no}` — Beneficiary Lookup: returns every
     scheme this voter appears in.
   - `GET /beneficiaries/by-geography` — backed by `v_beneficiaries_by_geography`.
6. **Multimedia** — separate CRUD routers for Gallery photos, MP3 songs
   (handle file upload + duration + play/download counters), Videos (support
   both YouTube URL and file upload, per the source toggle), Press gallery.
7. **Surveys & Feedback** — CRUD, filter by mandal/category/rating.
8. **Events** — CRUD; `GET /events/upcoming` (event_date >= today).
9. **Notes & Follow-ups** — CRUD, filter by priority/status/due date, can
   link to a voter by `epic_no` or free text.
10. **Local Leaders** — CRUD, filter by mandal/village/party.
11. **Janata Darbar** — CRUD, auto-generate `token_number` on create.
12. **Contact Us (public)** — `POST /contact` (public, unauthenticated) and
    `GET /contact-messages` (staff-only, list/filter by status). The public
    POST must support the Voter-ID autofill flow: add a public
    `GET /public/voter-lookup/{epic_no}` endpoint that returns
    Name/Mobile/Village/Mandal if the EPIC exists, 404 if not (frontend falls
    back to manual entry on 404).
13. **Achievements** — CRUD (public list, staff-managed).
14. **Reports** — `GET /reports/summary` (total beneficiaries, total amount
    disbursed, events conducted, pending requests, each with month-over-month
    delta), `GET /reports/scheme-performance` (`v_scheme_performance`),
    `GET /reports/applications-trend` (applications over time, grouped by
    month).
15. **Dashboard Home** — one aggregating `GET /dashboard/summary` endpoint
    that returns all the KPI cards + both donut charts + the 10 most recent
    `activity_log` entries in a single response, to minimize frontend
    round-trips.
16. **Staff Management** — CRUD on `staff_users` (super_admin only can
    create/delete other staff; creating a user hashes the password).
17. **Settings** — GET/PUT on `app_settings` (single-row table).

## Activity logging

Every create/update/delete on voters, development_works, beneficiaries, and
CM Relief Fund specifically must insert a row into `activity_log` (actor,
action_type, module, reference_id, description). Wire this as a reusable
dependency or service method, not copy-pasted into every route.

## File uploads

Photos/videos/documents (voter photos, beneficiary photos/documents/CMRF
videos, gallery photos, MP3s, event photos, press photos, Janata Darbar
documents) — implement local disk storage under an `/uploads` directory
behind a static file route for now, but structure the storage access behind
an interface/service so I can swap in S3-compatible object storage later
without touching route code.

## Validation & data integrity

- `epic_no` uniqueness enforced on voters; every table that stores `epic_no`
  without a hard FK (beneficiaries, surveys, notes_followups, etc.) should
  still validate the *format* of the EPIC number even when the voter doesn't
  exist yet.
- Aadhaar numbers: encrypt at rest (application-level, e.g. `cryptography`
  Fernet with a key from env) — never store plain. Mask in all API responses
  except a single explicit "reveal" endpoint restricted to super_admin.
- Mobile numbers: validate as 10-digit Indian mobile format.

## CORS & deployment

- Enable CORS for `https://mlainr.com` and `https://mla-inr.netlify.app` (and
  `http://localhost:3000` for local dev).
- Provide a `Dockerfile` and `docker-compose.yml` (app + Postgres) for local
  dev, plus clear instructions for deploying to a GoDaddy Managed VPS running
  CyberPanel (systemd service for Uvicorn behind Nginx, or Docker — your
  call, tell me which you'd recommend and why) as well as notes on deploying
  to Render with a Neon Postgres connection string instead, since I'm
  deciding between the two.
- `.env.example` with every required variable documented.

## What I want from you as output

1. The full FastAPI project, working end-to-end against the provided schema.
2. Alembic migration(s) that produce exactly the schema in `schema.sql` (plus
   the seed data from `seed_geography.sql` as a separate, re-runnable seed
   script, not baked into a migration).
3. A `README.md` covering: local setup, running migrations, running the seed
   script, environment variables, how auth/roles work, and how to add a new
   welfare scheme (since `scheme_details` is JSONB, this should be config,
   not a schema change).
4. Auto-generated OpenAPI docs (FastAPI gives you this for free — just make
   sure every route has a clear summary/description and correct response
   models).

Ask me before making structural changes to `schema.sql` — otherwise use it as
the source of truth. Start by reading all three attached files in full, then
give me a short plan (project structure + migration approach) before you
start writing code.
