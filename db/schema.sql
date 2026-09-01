-- ============================================================================
-- INR MLA CRM — Database Schema (PostgreSQL)
-- Constituency: 109-Kandukur | Mandals: Kandukur, Lingasamudram, Gudluru,
--               Ulavapadu, Voletivaripalem
-- Designed to sit behind FastAPI + Alembic, same stack as the INTURI backend.
-- ============================================================================

-- Enables fast fuzzy/partial name search on voters (used by search/autocomplete)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================================
-- 1. GEOGRAPHY — everything else hangs off mandal_id / village_id
-- ============================================================================

CREATE TABLE mandals (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE villages (
    id          SERIAL PRIMARY KEY,
    mandal_id   INT NOT NULL REFERENCES mandals(id) ON DELETE RESTRICT,
    name        VARCHAR(150) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (mandal_id, name)
);
CREATE INDEX idx_villages_mandal ON villages(mandal_id);

-- Alternate spellings of a village name accepted on bulk-import lookups, so
-- real electoral-roll sheets (inconsistent casing/spelling) resolve to the
-- same village_id instead of needing every sheet renamed to match exactly.
CREATE TABLE village_aliases (
    id          SERIAL PRIMARY KEY,
    village_id  INT NOT NULL REFERENCES villages(id) ON DELETE CASCADE,
    mandal_id   INT NOT NULL REFERENCES mandals(id) ON DELETE CASCADE,
    alias       VARCHAR(150) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (mandal_id, alias)
);
CREATE INDEX idx_village_aliases_village ON village_aliases(village_id);

CREATE TABLE booths (
    id                    SERIAL PRIMARY KEY,
    booth_number          VARCHAR(20) NOT NULL,
    booth_name            VARCHAR(150),
    village_id            INT NOT NULL REFERENCES villages(id) ON DELETE RESTRICT,
    mandal_id             INT NOT NULL REFERENCES mandals(id) ON DELETE RESTRICT,
    location_address      TEXT,
    total_voters          INT DEFAULT 0,
    booth_officer_name    VARCHAR(150),
    booth_officer_mobile  VARCHAR(15),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (mandal_id, booth_number)
);
CREATE INDEX idx_booths_village ON booths(village_id);
CREATE INDEX idx_booths_mandal ON booths(mandal_id);

-- ============================================================================
-- 2. AUTH / STAFF — Super Admin & Admin login, Staff Management module
-- ============================================================================

CREATE TABLE staff_users (
    id             SERIAL PRIMARY KEY,
    name           VARCHAR(150) NOT NULL,
    email          VARCHAR(150) NOT NULL UNIQUE,
    password_hash  VARCHAR(255) NOT NULL,
    role           VARCHAR(20) NOT NULL CHECK (role IN ('super_admin','admin')),
    mobile         VARCHAR(15),
    status         VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active','inactive')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- 3. VOTERS — the spine of the whole system. Every other module links back
--    here (or at minimum stores epic_no) so a Voter-ID lookup can pull a
--    full 360° profile in one pass.
-- ============================================================================

CREATE TABLE voters (
    id                     SERIAL PRIMARY KEY,
    epic_no                VARCHAR(20) NOT NULL UNIQUE,   -- "Voter ID"
    name                   VARCHAR(150) NOT NULL,
    relation_name          VARCHAR(150),                  -- father's/husband's name
    age                    INT,
    gender                 VARCHAR(10) CHECK (gender IN ('Male','Female','Other')),
    mobile                 VARCHAR(15),
    aadhaar_number         VARCHAR(20),
    house_no               VARCHAR(50),
    village_id             INT NOT NULL REFERENCES villages(id),
    mandal_id              INT NOT NULL REFERENCES mandals(id),
    booth_id               INT REFERENCES booths(id),
    voted_last_election    BOOLEAN,
    is_new_voter           BOOLEAN NOT NULL DEFAULT false,   -- current-year new registration
    photo_url              TEXT,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_voters_mandal ON voters(mandal_id);
CREATE INDEX idx_voters_village ON voters(village_id);
CREATE INDEX idx_voters_booth ON voters(booth_id);
CREATE INDEX idx_voters_name_trgm ON voters USING gin (name gin_trgm_ops);

-- ============================================================================
-- 4. DEVELOPMENT WORKS
-- ============================================================================

CREATE TABLE development_works (
    id              SERIAL PRIMARY KEY,
    title           VARCHAR(255) NOT NULL,
    category        VARCHAR(100),
    mandal_id       INT NOT NULL REFERENCES mandals(id),
    village_id      INT REFERENCES villages(id),
    estimated_cost  NUMERIC(14,2),
    description     TEXT,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','in_progress','completed')),
    work_date       DATE,
    created_by      INT REFERENCES staff_users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_devworks_mandal ON development_works(mandal_id);
CREATE INDEX idx_devworks_status ON development_works(status);

-- ============================================================================
-- 5. SCHEMES + BENEFICIARIES
--    schemes         = master list (powers the public "Super Six" pages)
--    beneficiaries   = ONE shared table for every scheme's common fields,
--                      with a JSONB column for the handful of fields that
--                      are unique to a given scheme. See notes at bottom.
-- ============================================================================

CREATE TABLE schemes (
    id                     SERIAL PRIMARY KEY,
    scheme_code            VARCHAR(50) NOT NULL UNIQUE,  -- 'cmrf', 'aadabidda_nidhi', ...
    scheme_name            VARCHAR(150) NOT NULL,
    short_description      TEXT,
    detailed_description   TEXT,
    badge_text             VARCHAR(100),
    service_provider       VARCHAR(150),
    category                VARCHAR(100),
    launch_date            DATE,
    status                 VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active','inactive')),
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE beneficiaries (
    id                    SERIAL PRIMARY KEY,
    scheme_id             INT NOT NULL REFERENCES schemes(id),
    voter_id              INT REFERENCES voters(id),      -- linked when the EPIC matches an existing voter
    epic_no               VARCHAR(20),                     -- always captured, even if voter_id is NULL
    beneficiary_name      VARCHAR(150) NOT NULL,           -- also holds "Head of Household" / "Mother's Name" / "Farmer Name" etc.
    relation_name         VARCHAR(150),
    age                   INT,
    gender                VARCHAR(10),
    aadhaar_number        VARCHAR(20),
    mobile_number         VARCHAR(15),
    bank_account_number   VARCHAR(30),
    ifsc_code             VARCHAR(15),
    amount                NUMERIC(12,2),                   -- monthly/annual amount as applicable
    village_id            INT NOT NULL REFERENCES villages(id),
    mandal_id             INT NOT NULL REFERENCES mandals(id),
    application_date      DATE,
    status                VARCHAR(20) NOT NULL DEFAULT 'pending'
                              CHECK (status IN ('pending','approved','rejected','disbursed')),
    photo_url             TEXT,
    document_url          TEXT,
    video_url             TEXT,                            -- CMRF: proof-of-disbursement video
    remarks               TEXT,
    scheme_details        JSONB NOT NULL DEFAULT '{}',      -- scheme-specific fields, see notes below
    created_by            INT REFERENCES staff_users(id),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_beneficiaries_scheme ON beneficiaries(scheme_id);
CREATE INDEX idx_beneficiaries_mandal ON beneficiaries(mandal_id);
CREATE INDEX idx_beneficiaries_village ON beneficiaries(village_id);
CREATE INDEX idx_beneficiaries_voter ON beneficiaries(voter_id);
CREATE INDEX idx_beneficiaries_epic ON beneficiaries(epic_no);
CREATE INDEX idx_beneficiaries_details_gin ON beneficiaries USING gin (scheme_details);

-- scheme_details JSONB layout, by scheme_code (documented here, enforced in the API layer):
--   cmrf                  -> {}  (no extra fields — everything is in the core columns)
--   aadabidda_nidhi       -> {}  (monthly amount is the core "amount" column)
--   thalliki_vandanam     -> {"student_name": "...", "school_name": "...", "class_grade": "..."}
--   deepam_scheme         -> {"ration_card_number": "...", "gas_connection_number": "...", "gas_agency": "..."}
--   maha_shakthi          -> {"bus_pass_number": "...", "preferred_route": "...", "depot": "..."}
--   annadata_sukhibhava   -> {"land_extent_acres": 2.5, "survey_number": "..."}
--   yuvagalam             -> {"qualification": "..."}

-- ============================================================================
-- 6. MULTIMEDIA
-- ============================================================================

CREATE TABLE gallery_photos (
    id           SERIAL PRIMARY KEY,
    title        VARCHAR(200),
    category     VARCHAR(50) CHECK (category IN ('leaders','events','spiritual','inaugurations','sports','others')),
    photo_url    TEXT NOT NULL,
    caption      TEXT,
    status       VARCHAR(20) NOT NULL DEFAULT 'active',
    date_added   DATE NOT NULL DEFAULT CURRENT_DATE,
    created_by   INT REFERENCES staff_users(id)
);

CREATE TABLE mp3_songs (
    id                SERIAL PRIMARY KEY,
    title             VARCHAR(200) NOT NULL,
    file_url          TEXT NOT NULL,
    file_name         VARCHAR(255),
    duration_seconds  INT,
    description       TEXT,
    play_count        INT NOT NULL DEFAULT 0,
    download_count    INT NOT NULL DEFAULT 0,
    status            VARCHAR(20) NOT NULL DEFAULT 'active',
    date_added        DATE NOT NULL DEFAULT CURRENT_DATE
);

CREATE TABLE videos (
    id               SERIAL PRIMARY KEY,
    title            VARCHAR(200) NOT NULL,
    video_source     VARCHAR(20) NOT NULL CHECK (video_source IN ('youtube','upload')),
    youtube_url      TEXT,
    video_file_url   TEXT,
    description      TEXT,
    status           VARCHAR(20) NOT NULL DEFAULT 'active',
    upload_date      DATE NOT NULL DEFAULT CURRENT_DATE
);

CREATE TABLE press_gallery (
    id           SERIAL PRIMARY KEY,
    title        VARCHAR(200) NOT NULL,
    photo_url    TEXT,
    caption      TEXT,
    status       VARCHAR(20) NOT NULL DEFAULT 'active',
    date_added   DATE NOT NULL DEFAULT CURRENT_DATE
);

-- ============================================================================
-- 7. SURVEYS & FEEDBACK
-- ============================================================================

CREATE TABLE surveys (
    id                   SERIAL PRIMARY KEY,
    respondent_name      VARCHAR(150),
    mobile_number        VARCHAR(15),
    voter_id             INT REFERENCES voters(id),
    epic_no              VARCHAR(20),
    category             VARCHAR(50),
    feedback_type        VARCHAR(50),
    satisfaction_rating  SMALLINT CHECK (satisfaction_rating BETWEEN 1 AND 5),
    village_id           INT REFERENCES villages(id),
    mandal_id            INT REFERENCES mandals(id),
    survey_date          DATE NOT NULL DEFAULT CURRENT_DATE,
    status               VARCHAR(20) NOT NULL DEFAULT 'pending',
    photo_url            TEXT,
    feedback_details     TEXT,
    created_by           INT REFERENCES staff_users(id)
);
CREATE INDEX idx_surveys_mandal ON surveys(mandal_id);

-- ============================================================================
-- 8. EVENTS (includes upcoming events — filter on event_date >= CURRENT_DATE)
-- ============================================================================

CREATE TABLE events (
    id                    SERIAL PRIMARY KEY,
    event_title           VARCHAR(200) NOT NULL,
    event_type            VARCHAR(100),
    venue                 VARCHAR(200),
    chief_guest           VARCHAR(150),
    village_id            INT REFERENCES villages(id),
    mandal_id             INT REFERENCES mandals(id),
    event_date            DATE NOT NULL,
    event_time            TIME,
    expected_attendance   INT,
    status                VARCHAR(20) NOT NULL DEFAULT 'upcoming'
                              CHECK (status IN ('upcoming','completed','cancelled')),
    photo_url             TEXT,
    description           TEXT,
    created_by            INT REFERENCES staff_users(id)
);
CREATE INDEX idx_events_date ON events(event_date);

-- ============================================================================
-- 9. NOTES & FOLLOW-UPS
-- ============================================================================

CREATE TABLE notes_followups (
    id                 SERIAL PRIMARY KEY,
    subject            VARCHAR(200),
    related_person     VARCHAR(150),
    voter_id           INT REFERENCES voters(id),
    epic_no            VARCHAR(20),
    mobile_number      VARCHAR(15),
    category           VARCHAR(50),
    priority           VARCHAR(10) CHECK (priority IN ('low','medium','high')),
    due_date           DATE,
    status             VARCHAR(20) NOT NULL DEFAULT 'open' CHECK (status IN ('open','in_progress','closed')),
    village_id         INT REFERENCES villages(id),
    mandal_id          INT REFERENCES mandals(id),
    notes_description  TEXT,
    created_by         INT REFERENCES staff_users(id),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- 10. LOCAL LEADERS
-- ============================================================================

CREATE TABLE local_leaders (
    id               SERIAL PRIMARY KEY,
    leader_name      VARCHAR(150) NOT NULL,
    alias_name       VARCHAR(150),
    position         VARCHAR(100),
    party            VARCHAR(100),
    voter_id         INT REFERENCES voters(id),
    epic_no          VARCHAR(20),
    aadhaar_number   VARCHAR(20),
    mobile_number    VARCHAR(15),
    village_id       INT NOT NULL REFERENCES villages(id),
    mandal_id        INT NOT NULL REFERENCES mandals(id),
    date_joined      DATE,
    status           VARCHAR(20) NOT NULL DEFAULT 'active',
    photo_url        TEXT,
    remarks          TEXT
);

-- ============================================================================
-- 11. JANATA DARBAR (grievance sessions)
-- ============================================================================

CREATE TABLE janata_darbar_visits (
    id                  SERIAL PRIMARY KEY,
    token_number        VARCHAR(20) NOT NULL UNIQUE,
    visitor_name        VARCHAR(150) NOT NULL,
    mobile_number       VARCHAR(15),
    voter_id            INT REFERENCES voters(id),
    epic_no             VARCHAR(20),
    age                 INT,
    gender              VARCHAR(10),
    issue_category      VARCHAR(100),
    village_id          INT REFERENCES villages(id),
    mandal_id           INT REFERENCES mandals(id),
    visit_date          DATE NOT NULL DEFAULT CURRENT_DATE,
    status              VARCHAR(20) NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending','in_progress','resolved','referred')),
    document_url        TEXT,
    issue_description   TEXT,
    action_taken        TEXT
);

-- ============================================================================
-- 12. CONTACT US (public form — this is what auto-fills from Voter ID)
-- ============================================================================

CREATE TABLE contact_messages (
    id              SERIAL PRIMARY KEY,
    voter_id        INT REFERENCES voters(id),
    epic_no         VARCHAR(20),
    name            VARCHAR(150),
    mobile_number   VARCHAR(15),
    village_id      INT REFERENCES villages(id),
    mandal_id       INT REFERENCES mandals(id),
    message         TEXT NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'new' CHECK (status IN ('new','read','responded')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- 13. ACHIEVEMENTS (public Achievements page)
-- ============================================================================

CREATE TABLE achievements (
    id           SERIAL PRIMARY KEY,
    title        VARCHAR(200) NOT NULL,
    description  TEXT,
    category     VARCHAR(100),
    photo_url    TEXT,
    status       VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- 14. ACTIVITY LOG — powers the "Recent Activities" feed on Dashboard Home
-- ============================================================================

CREATE TABLE activity_log (
    id             SERIAL PRIMARY KEY,
    actor_id       INT REFERENCES staff_users(id),
    action_type    VARCHAR(50),   -- 'voter_added','work_added','beneficiary_added','cmrf_contribution', etc.
    module         VARCHAR(50),
    reference_id   INT,
    description    TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_activity_created ON activity_log(created_at DESC);

-- ============================================================================
-- 15. SETTINGS — Constituency Information tab + Voters module snapshot
-- ============================================================================

CREATE TABLE app_settings (
    id                       SERIAL PRIMARY KEY,
    constituency_name        VARCHAR(150),
    constituency_no          VARCHAR(20),
    state                    VARCHAR(100),
    district                 VARCHAR(100),
    lok_sabha_constituency   VARCHAR(150),
    current_mla              VARCHAR(150),
    year_established         INT,
    total_mandals            INT,
    total_villages           INT,
    total_population         BIGINT,
    office_address           TEXT,
    contact_email            VARCHAR(150),
    contact_phone            VARCHAR(15)
);

-- ============================================================================
-- 16. REPORTING VIEWS — power the KPI cards / donut charts / tables directly,
--     no extra tables or app-side aggregation needed.
-- ============================================================================

-- Voters module: "Mandal-wise Voter Summary Table"
CREATE VIEW v_mandal_voter_summary AS
SELECT
    m.id                                                   AS mandal_id,
    m.name                                                 AS mandal_name,
    COUNT(*) FILTER (WHERE v.gender = 'Male')               AS male_voters,
    COUNT(*) FILTER (WHERE v.gender = 'Female')             AS female_voters,
    COUNT(v.id)                                             AS total_voters,
    ROUND(100.0 * COUNT(v.id) / NULLIF(SUM(COUNT(v.id)) OVER (), 0), 2) AS pct_of_total
FROM mandals m
LEFT JOIN voters v ON v.mandal_id = m.id
GROUP BY m.id, m.name;

-- Dashboard Home: Voter Gender Distribution donut
CREATE VIEW v_voter_gender_distribution AS
SELECT gender, COUNT(*) AS total
FROM voters
GROUP BY gender;

-- Dashboard Home: Development Works Overview donut
CREATE VIEW v_development_status_summary AS
SELECT status, COUNT(*) AS total
FROM development_works
GROUP BY status;

-- Beneficiaries by mandal/village, across every scheme — answers
-- "how many members got government benefits, in which mandal/village"
CREATE VIEW v_beneficiaries_by_geography AS
SELECT
    mn.name  AS mandal_name,
    vl.name  AS village_name,
    s.scheme_name,
    b.status,
    COUNT(*) AS beneficiary_count,
    SUM(b.amount) AS total_amount
FROM beneficiaries b
JOIN mandals mn ON mn.id = b.mandal_id
JOIN villages vl ON vl.id = b.village_id
JOIN schemes s ON s.id = b.scheme_id
GROUP BY mn.name, vl.name, s.scheme_name, b.status;

-- Reports module: "Scheme-wise Performance Table"
CREATE VIEW v_scheme_performance AS
SELECT
    s.scheme_name,
    COUNT(b.id)                                              AS total_applications,
    COUNT(*) FILTER (WHERE b.status = 'approved')             AS approved,
    COUNT(*) FILTER (WHERE b.status = 'pending')               AS pending,
    COALESCE(SUM(b.amount) FILTER (WHERE b.status = 'disbursed'), 0) AS amount_disbursed,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE b.status = 'approved') / NULLIF(COUNT(b.id), 0), 2
    ) AS approval_rate_pct
FROM schemes s
LEFT JOIN beneficiaries b ON b.scheme_id = s.id
GROUP BY s.scheme_name;

-- "Voter 360" — enter an EPIC number, get every module that touches that
-- person in one shot. This is the query behind the Voter-ID autofill on
-- Contact Us, Beneficiary Lookup, Notes & Follow Ups, etc.
-- Usage: SELECT * FROM voters WHERE epic_no = :epic;
--        SELECT * FROM beneficiaries WHERE epic_no = :epic;
--        SELECT * FROM notes_followups WHERE epic_no = :epic;
--        SELECT * FROM janata_darbar_visits WHERE epic_no = :epic;
--        SELECT * FROM surveys WHERE epic_no = :epic;
-- (kept as separate queries rather than one giant join so the API can
--  fetch each panel independently and stay fast)
