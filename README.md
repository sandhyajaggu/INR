# INR MLA CRM — Backend

FastAPI + PostgreSQL backend for the INR MLA CRM constituency management
platform (109-Kandukur: Kandukur, Lingasamudram, Gudluru, Ulavapadu,
Voletivaripalem mandals). Serves the existing React frontend at
[mlainr.com](https://mlainr.com/).

Source-of-truth documents this backend was built from live in `docs/` and
`db/`:
- `docs/claude_code_prompt.md` — the build brief.
- `docs/INR_MLA_CRM_Project_Documentation.docx` — full functional spec (every
  page, every table's columns, every Add/Edit form's fields).
- `db/schema.sql` — the 22-table + 5-view PostgreSQL schema (source of truth
  for the data model; SQLAlchemy models in `app/models/` mirror it exactly).
- `db/seed_geography.sql` — original SQL seed; `scripts/seed_geography.py` is
  the re-runnable Python equivalent used in practice. `db/seed_village_aliases.sql`
  / `scripts/seed_village_aliases.py` seed known alternate village-name spellings.

## Project structure

```
app/
  core/            config, DB session, JWT/security, file storage, generic CRUD router, DI
  models/          SQLAlchemy models — one file per domain, mirrors schema.sql
  schemas/         Pydantic v2 request/response schemas
  services/        business logic (auth, voters, beneficiaries, activity log, encryption, reports)
  api/routes/       one router per sidebar module
  main.py          app assembly: CORS, static /uploads mount, router wiring
alembic/           migrations (env.py wired to app.core.config + all models)
scripts/           seed_geography.py, seed_village_aliases.py, seed_schemes.py — re-runnable seeds
db/                original schema.sql / seed_geography.sql / seed_village_aliases.sql for reference
docs/              original spec documents for reference
uploads/           local file storage root (gitignored; swap for S3 later via app/core/storage.py)
```

Most dashboard modules (Booths, Development Works, Schemes Master, Gallery,
MP3, Videos, Press, Surveys & Feedback, Events, Notes & Follow Ups, Local
Leaders) share one generic paginated CRUD implementation in
`app/core/crud_router.py` so the same list/filter/create/update/delete logic
isn't hand-copied 11 times. Modules with real bespoke logic — Voters (fuzzy
search, EPIC uniqueness, Aadhaar encryption), Beneficiaries (see below),
Staff (password hashing, super_admin-only), Janata Darbar (auto token
number), Local Leaders (Aadhaar), Achievements (public read), Contact Us,
Reports, Dashboard, Settings — get their own router.

### Beneficiaries — one router per scheme, not one generic endpoint

Each of the 7 welfare schemes (CMRF, Aadabidda Nidhi, Thalliki Vandanam,
Deepam Scheme, Maha Shakthi, Annadata Sukhibhava, Yuvagalam) has genuinely
different Add/Edit form fields per the functional spec — e.g. Thalliki
Vandanam needs `student_name`/`school_name`/`class_grade`, Deepam needs
`ration_card_number`/`gas_connection_number`/`gas_agency`. Rather than hide
that behind one shared `POST /beneficiaries` endpoint with a generic
`scheme_details: {}` blob, each scheme gets its own router with those exact
fields as real top-level request fields:

```
POST /beneficiaries/cmrf                  {beneficiary_name, amount, video_url, ...}
POST /beneficiaries/thalliki-vandanam     {mother_name, student_name, school_name, class_grade, ...}
POST /beneficiaries/deepam-scheme         {head_of_household_name, ration_card_number, gas_agency, ...}
... etc for maha-shakthi, annadata-sukhibhava, yuvagalam, aadabidda-nidhi
```

All 7 still read/write the single shared `beneficiaries` table from
`db/schema.sql` — nothing about the DB schema changed. The factory in
`app/core/beneficiary_scheme_router.py` maps each scheme's fields onto that
table automatically: the scheme's "name" field (e.g. `mother_name`) becomes
`beneficiary_name`, anything matching a real column (`amount`, `status`,
`aadhaar_number`, ...) goes there directly, and everything else
(`student_name`, `school_name`, ...) is packed into the `scheme_details`
JSONB column. Cross-scheme operations stay on the generic
`app/api/routes/beneficiaries.py` router, because they're inherently
cross-scheme: `GET /beneficiaries` (list across all schemes),
`GET /beneficiaries/lookup/{epic_no}` (Beneficiary Lookup), and
`GET /beneficiaries/by-geography`.

Run `python -m scripts.seed_schemes` once (idempotent) to seed the 7 scheme
rows — the per-scheme routers 500 with a clear message if a scheme_code
isn't seeded yet.

### Mandal/village input: names, not IDs

Every create/update request across every module takes `mandal_name` and
`village_name` (e.g. `"Kandukur"`) instead of numeric `mandal_id`/
`village_id` — `app/services/geography_service.py` resolves them to the
internal IDs server-side (404 if the name doesn't match a seeded
mandal/village). The DB schema itself is untouched (still FK'd by ID); this
is purely an API-boundary convenience so callers never need to know or look
up internal IDs. Because village names are only unique *within* a mandal
(schema.sql's own `UNIQUE (mandal_id, name)` constraint), village lookups
always require `mandal_name` alongside `village_name` — submitting a village
name without its mandal is rejected. List-endpoint query-string filters
(`?mandal_id=`) were left as IDs, since that's a separate concern from
create/update payloads.

## Local setup

1. **Install PostgreSQL 15+** (or use the bundled `docker-compose.yml`). The
   `pg_trgm` extension is created automatically by the first migration.
2. **Create a virtualenv and install deps:**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate        # Windows
   pip install -r requirements.txt
   ```
3. **Copy `.env.example` to `.env`** and fill in real values:
   ```bash
   cp .env.example .env
   python -c "import secrets; print(secrets.token_urlsafe(64))"   # SECRET_KEY, CAPTCHA_SECRET_KEY
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # AADHAAR_ENCRYPTION_KEY
   ```
4. **Apply migrations and seed geography + schemes:**
   ```bash
   python -m alembic upgrade head
   python -m scripts.seed_geography
   python -m scripts.seed_village_aliases
   python -m scripts.seed_schemes
   ```
5. **Create your first super_admin** (there's no seed for staff accounts —
   nothing should be able to self-register into `super_admin`):
   ```bash
   python -c "
   import asyncio
   from app.core.database import AsyncSessionLocal
   from app.core.security import hash_password
   from app.models.staff import StaffUser

   async def main():
       async with AsyncSessionLocal() as db:
           db.add(StaffUser(name='Admin', email='admin@example.com',
                             password_hash=hash_password('change-me'),
                             role='super_admin', status='active'))
           await db.commit()

   asyncio.run(main())
   "
   ```
6. **Start the server:**
   ```bash
   uvicorn app.main:app --reload
   ```
   Docs at `http://localhost:8000/docs`.

### Running with Docker instead

```bash
docker compose up --build
```
This starts Postgres + the app, runs migrations, and seeds geography
automatically (see the `app` service's `command` in `docker-compose.yml`).

## Migrations (Alembic)

Two migrations are committed and were generated + applied against a real
Postgres 15 instance during initial setup (not just written blind):

- `36c1a5eee24d_initial_schema.py` — all 21 tables, generated by
  `alembic revision --autogenerate`. Two things autogenerate can't pick up on
  its own were added by hand: `CREATE EXTENSION IF NOT EXISTS pg_trgm` (the
  `idx_voters_name_trgm` GIN index itself *is* defined on the `Voter` model,
  so autogenerate does emit that correctly — only the extension statement
  needed adding), and the 5 reporting views from `db/schema.sql` section 16
  (`v_mandal_voter_summary`, `v_voter_gender_distribution`,
  `v_development_status_summary`, `v_beneficiaries_by_geography`,
  `v_scheme_performance`) — these live outside the SQLAlchemy model layer
  entirely (queried via raw SQL in the relevant routes), so autogenerate has
  no way to know about them.
- `7e55ce0a46f5_add_server_side_column_defaults.py` — adds a real DB-level
  `server_default` (not just an ORM-side Python default) for every column
  `db/schema.sql` declares a literal `DEFAULT` on that was missing one
  (`status`, `total_voters`, `play_count`/`download_count`,
  `is_new_voter`, `scheme_details`). Worth knowing: `alembic/env.py` turns on
  `compare_server_default=True` so autogenerate can actually detect this kind
  of drift going forward — but that setting has a documented false-positive:
  it can't reliably compare function-based defaults like `now()`, so **every**
  future `--autogenerate` run will propose touching every `created_at`/
  `updated_at` column even though nothing changed. This migration was
  hand-trimmed to drop those spurious lines (its raw autogenerate output also
  baked a hardcoded timestamp literal into `downgrade()` instead of reverting
  to `now()`, which would have been actively wrong to apply). **Always review
  an autogenerate diff before applying it** — drop any `now()`-only
  alter_column pairs it proposes.

One real schema.sql bug was caught and fixed along the way:
`v_mandal_voter_summary.total_voters` used `COUNT(*)` over a `LEFT JOIN`,
which counts a phantom row for mandals with zero voters (reports `1` instead
of `0`). Fixed to `COUNT(v.id)` in both `db/schema.sql` and the migration.

For new schema changes: edit the SQLAlchemy model, then
`alembic revision --autogenerate -m "..."`, review the diff (see the
`now()` caveat above), then `alembic upgrade head` — never hand-write raw SQL
migrations.

## Seeding geography

```bash
python -m scripts.seed_geography
python -m scripts.seed_village_aliases
```

Both idempotent (`ON CONFLICT DO NOTHING`) — safe to re-run.
`seed_geography` seeds the 5 mandals and every village in the constituency,
matching `db/seed_geography.sql` exactly. `seed_village_aliases` (must run
after) seeds known alternate spellings of those village names — real
electoral-roll sheets use inconsistent casing/spelling, and an alias lets
bulk-import resolve either spelling to the same village_id instead of every
sheet needing to be renamed to match `villages.name` exactly. See
`scripts/seed_village_aliases.py` to add a new alias.

## Environment variables

See `.env.example` for the full list with comments. Highlights:

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Signs JWT access/refresh tokens |
| `CAPTCHA_SECRET_KEY` | Signs the short-lived CAPTCHA token (separate key so captcha tokens can't be reused as auth tokens) |
| `AADHAAR_ENCRYPTION_KEY` | Fernet key — Aadhaar numbers are encrypted at rest with this |
| `DATABASE_URL` | `postgresql+asyncpg://...` — point at Neon for the Render deployment |
| `CORS_ORIGINS` | Comma-separated; defaults to `mlainr.com`, the Netlify staging URL, and localhost |
| `UPLOAD_DIR` / `UPLOAD_BASE_URL` | Local disk storage root + the public path it's mounted at |

## How auth & roles work

- `GET /auth/captcha` returns `{question, captcha_token}` — a signed,
  short-lived (5 min) JWT embedding the expected answer. Nothing is stored
  server-side.
- `POST /auth/login` takes `{role, email, password, captcha_token,
  captcha_answer}`. The CAPTCHA is verified first (signature + expiry +
  answer match), then credentials against `staff_users` filtered by both
  `email` **and** the submitted `role` (so a super_admin can't accidentally
  log in through the admin toggle with the wrong expectations).
- On success you get `{access_token, refresh_token, role, staff_id, name}`.
  Send `Authorization: Bearer <access_token>` on every subsequent request.
- `POST /auth/refresh` exchanges a valid refresh token for a new pair.
- `POST /auth/forgot-password` is a stub — returns a reset token directly
  instead of emailing it, per the brief. Wire up email delivery later by
  replacing the body of `issue_password_reset_token` in
  `app/services/auth_service.py`.
- **Role enforcement** happens via FastAPI dependencies in
  `app/core/dependencies.py`: `RequireStaff` (any authenticated
  super_admin/admin) gates create/update, `RequireSuperAdmin` gates every
  DELETE route — an `admin` token gets a 403, not a hidden/disabled button.

## Adding a new welfare scheme

Since `beneficiaries.scheme_details` is JSONB, adding scheme #8 is **config
and one new router file, not a migration**:

1. Insert a row into `schemes` (via `POST /schemes`, or add it to
   `scripts/seed_schemes.py`) with a new `scheme_code`.
2. Add a `Create`/`Update`/`Out` schema set to
   `app/schemas/beneficiary_schemes.py` with that scheme's exact fields —
   copy the shape of an existing one closest to it (e.g. copy `CmrfCreate` if
   it has no scheme-specific fields beyond the core columns, or
   `ThallikiVandanamCreate` if it needs a couple of extra fields).
3. Add a new thin route file under `app/api/routes/beneficiaries_<scheme>.py`
   (copy `beneficiaries_cmrf.py` — it's ~12 lines) calling
   `build_beneficiary_scheme_router(scheme_code=..., prefix=..., ...,
   name_field=...)`. `name_field` is whichever of your new schema's fields
   should map onto the `beneficiaries.beneficiary_name` column (e.g.
   `"mother_name"` for a maternal scheme); everything else that isn't a real
   `beneficiaries` column automatically lands in `scheme_details`.
4. Register the new router in `app/main.py`, **before** the generic
   `beneficiaries.router` (see the ordering note already there).

No `scheme_details` sub-schema registry to maintain by hand — the router
factory derives what goes in `scheme_details` directly from whatever fields
your new schema declares beyond the recognized core columns.

## Aadhaar handling

Encrypted at rest (Fernet, `AADHAAR_ENCRYPTION_KEY`) in `voters`,
`beneficiaries`, and `local_leaders`. Every list/get response returns
`aadhaar_masked` (e.g. `XXXXXXXX1234`), never the plaintext or ciphertext.
Each of those three modules has a `GET /{module}/{id}/aadhaar/reveal`
endpoint restricted to `super_admin` that decrypts and returns the plaintext
on demand.

## File uploads

`POST /files/upload` (multipart, staff-only) takes a file + a `subfolder`
and returns `{"url": "..."}`. Every module's create/update body then takes
that URL as a plain string field (`photo_url`, `document_url`, `video_url`,
`file_url`) — request bodies stay pure JSON everywhere else. Storage is
local disk today (`app/core/storage.py`'s `LocalDiskStorage`), served back
out under `/uploads` via `StaticFiles`; swapping to S3-compatible storage
later means implementing one more `FileStorage` subclass and changing
`get_file_storage()` — no route code changes.

## Deployment

### Option A — GoDaddy Managed VPS (CyberPanel)

Recommended shape: **Docker**, not a bare systemd Uvicorn process. CyberPanel
is primarily built around OpenLiteSpeed/PHP hosting; running the FastAPI app
in Docker (this repo's `Dockerfile`) keeps the Python/Postgres stack fully
isolated from CyberPanel's own runtime and lets you reuse the included
`docker-compose.yml` as-is. Steps:

1. Enable Docker in CyberPanel (or install Docker directly via SSH).
2. Clone this repo onto the VPS, set up `.env` with production secrets.
3. `docker compose up -d --build` (add `restart: unless-stopped`, already
   set, so it survives reboots).
4. In CyberPanel, create a reverse proxy vHost (or hand-write an OpenLiteSpeed
   / Nginx server block) forwarding `api.mlainr.com` → `127.0.0.1:8000`, with
   CyberPanel's free AutoSSL for the certificate.
5. Point the frontend's API base URL at `https://api.mlainr.com`.

Self-managed Postgres here means you own backups — set up `pg_dump` on a cron
job against the `db` container's volume, or point `DATABASE_URL` at a
separate managed Postgres instead of the bundled container.

### Option B — Render + Neon

`render.yaml` in the repo root is a ready-to-use Blueprint for this.

1. Create a Neon Postgres project, copy its connection string into
   `DATABASE_URL` (format:
   `postgresql+asyncpg://user:pass@ep-xxxx.neon.tech/dbname?ssl=require`).
2. On Render: New → Blueprint → point at this repo → it reads `render.yaml`
   and creates the web service (Docker runtime, the included `Dockerfile`,
   no build config needed). Alternatively, New → Web Service manually with
   the same settings.
3. Fill in the env vars marked `sync: false` in the Render dashboard
   (`SECRET_KEY`, `CAPTCHA_SECRET_KEY`, `AADHAAR_ENCRYPTION_KEY`,
   `DATABASE_URL`) — generate the first three with the commands in
   [Local setup](#local-setup) step 3.
4. `render.yaml`'s `preDeployCommand` already runs `alembic upgrade head &&
   python -m scripts.seed_geography && python -m scripts.seed_village_aliases
   && python -m scripts.seed_schemes` once per deploy, on a separate instance,
   before traffic cuts over — all four steps are idempotent. The container's
   `CMD` (`Dockerfile`) then just starts Uvicorn, which binds to Render's
   `$PORT` automatically.
5. Render issues TLS automatically; point the frontend at the Render URL (or
   a custom `api.mlainr.com` CNAME onto it).

**Uploads caveat:** `LocalDiskStorage` (`app/core/storage.py`) writes to
`/app/uploads` on the container's local disk, which Render wipes on every
deploy/restart unless a persistent disk is attached. `render.yaml` attaches a
1GB disk at `/app/uploads` for this reason — bump `sizeGB` if needed, or
switch to an S3-compatible `FileStorage` implementation later if uploads
volume outgrows a single disk (Render disks aren't shared across multiple
instances, which also caps this service at one instance as long as uploads
stay on local disk).

### Recommendation

**Render + Neon**, if there's no hard requirement to keep everything on the
existing GoDaddy box: managed Postgres (automatic backups, point-in-time
restore, connection pooling) and managed deploys (zero-downtime, automatic
TLS) remove almost all of the ops burden a small office team would otherwise
carry, and Neon's free/low tiers are plenty for a single-constituency CRM's
traffic. The GoDaddy/CyberPanel path is the right call only if there's a
specific reason to keep the API co-located with the existing static frontend
host or to avoid a second vendor — otherwise it trades lower monthly cost for
you personally owning Postgres backups, OS patching, and TLS renewal.

## OpenAPI docs

Every route has a `summary` (and most have a `description`) plus a typed
`response_model`, so `/docs` (Swagger UI) and `/redoc` are fully populated
without extra annotation work.
