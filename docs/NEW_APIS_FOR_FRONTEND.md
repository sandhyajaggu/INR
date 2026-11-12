# INR CRM — New Backend APIs for Frontend

As of 2026-11-12 (commit `0e57383`). Base URL: `https://inr-voua.onrender.com` · Swagger: `/docs`

Six API groups are live. Every existing field still works, so nothing breaks before you switch.
Protected endpoints need `Authorization: Bearer <access_token>`.

---

## 1. Login — `username` (email or mobile)

| Method | Endpoint | Auth | Change |
|---|---|---|---|
| POST | `/auth/login` | public | New `username` field: email **or** mobile. `email` still accepted. |
| POST | `/auth/forgot-password` | public | Also accepts `username`. |

```json
POST /auth/login
{ "role": "staff", "username": "9849355955", "password": "...", "captcha_token": "...", "captcha_answer": "12" }
```

- Mobile can be typed as `9849355955`, `+91 98493 55955` or `098493-55955`.
- Send `username` **or** `email`. Neither → `422`. Wrong details → `401 "Invalid credentials"`.
- Response is unchanged (`access_token`, `refresh_token`, `user`, ...).

---

## 2. Public settings — default language without login

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| GET | `/public/settings` | public | Default UI language + office profile for the public site |

```json
{
  "default_language": "te",
  "telugu_default_website": true,
  "profile":    { "constituency": "Kandukur (229)", "district": "...", "mla": "...", "office_phone": "...", "office_email": "...", "office_address": "..." },
  "profile_te": { "constituency": "...", "district": "...", "mla": "...", "office_phone": "...", "office_email": "...", "office_address": "..." }
}
```

- `default_language` is `"en"` or `"te"` — pass it straight to `i18n.changeLanguage()`.
- It follows the Settings page toggle **"Telugu default website"**.
- `GET /settings` is still login-only (unchanged).

---

## 3. Geography — mandal / village CRUD with Telugu names

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| GET | `/mandals` | login | List mandals |
| GET | `/mandals/{id}` | login | One mandal |
| POST | `/mandals` | Settings edit | Add mandal |
| PUT | `/mandals/{id}` | Settings edit | Rename / set Telugu name |
| DELETE | `/mandals/{id}` | Settings admin | Delete (only if unused) |
| GET | `/villages?mandal_name=Kandukur` | login | Villages of a mandal (or `?mandal_id=1`; no filter = all) |
| GET | `/villages/{id}` | login | One village |
| POST | `/villages` | Settings edit | Add village |
| PUT | `/villages/{id}` | Settings edit | Rename / Telugu name / move to another mandal |
| DELETE | `/villages/{id}` | Settings admin | Delete (only if unused) |
| GET | `/public/mandals` | public | Mandals for public forms (Contact page) |
| GET | `/public/villages?mandal_name=...` | public | Villages for public forms |

```json
GET /mandals
[ { "id": 1, "name": "Kandukur", "name_te": "కందుకూరు", "village_count": 42, "created_at": "..." } ]

GET /villages?mandal_name=Kandukur
[ { "id": 12, "name": "Palur", "name_te": "పాలూరు", "mandal_id": 1, "mandal": "Kandukur", "mandal_te": "కందుకూరు", "created_at": "..." } ]

POST /mandals    { "name": "Kandukur", "name_te": "కందుకూరు" }
POST /villages   { "mandal": "Kandukur", "name": "Palur", "name_te": "పాలూరు" }     // or "mandal_id": 1
PUT  /villages/12 { "name_te": "పాలూరు" }                                          // send only what changes
```

- `name` is unchanged, so the current `useGeography` dropdowns keep working. Show `name_te` when the UI is Telugu.
- Duplicate name → `409`. Deleting a mandal that still has villages, or anything used by voters/booths/etc. → `409` with a message.
- Delete returns `{ "success": true }`.

---

## 4. Surveys — percentage keys

| Endpoint | New keys |
|---|---|
| `GET /survey-campaigns` (also returned by create / update / response endpoints) | `positive_pct`, `negative_pct`, `completion_pct` |
| `GET /voter-surveys/summary` | `positivePct`, `negativePct` |

```json
{ "id": "CAMP-1", "positive": 9, "negative": 3, "responses": 12, "target": 40,
  "positive_pct": 75.0, "negative_pct": 25.0, "completion_pct": 30.0, ... }
```

- `positive_pct` / `negative_pct` = share of positive + negative answers (same formula as `Surveys.jsx` today).
- `completion_pct` = responses ÷ target, capped at 100.
- Summary % is out of `totalSurveys`.
- One decimal; `0.0` when there's nothing to divide by. You can remove the client-side math.

---

## 5. Files — full CRUD

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| POST | `/files/upload?subfolder=gallery` | super_admin / admin | Upload (multipart `file`) |
| GET | `/files?subfolder=&q=&content_type=&page=1&page_size=50` | login | List uploads, newest first |
| GET | `/files/{id}` | login | One file |
| PUT | `/files/{id}` | super_admin / admin | Replace content (multipart `file`) and/or rename (form field `name`) |
| DELETE | `/files/{id}` | super_admin / admin | Delete file + record |

`subfolder`: `voters, beneficiaries, gallery, mp3, videos, press, events, surveys, local_leaders, janata_darbar, achievements`

```json
POST /files/upload  →
{ "id": "FILE-7", "url": "/uploads/gallery/ab12.png", "subfolder": "gallery", "name": "photo.png",
  "content_type": "image/png", "size": 20480, "uploaded_by": "Admin", "created_at": "...", "updated_at": "..." }

GET /files  →  { "items": [ ...same shape... ], "total": 120, "page": 1, "page_size": 50, "pages": 3 }

PUT /files/FILE-7  →  { ...same shape..., "url_changed": false }
```

- Upload still returns `url` as before (plus `id` now).
- Replacing with the **same file type keeps the URL**, so records that store it keep working. A different type gets a new URL and `"url_changed": true` — update the record that holds the old URL.
- Max size per file: 25 MB (`413` if larger).
- Files uploaded before 2026-11-12 are not in the list.

---

## 6. Notifications — bell and sidebar badges

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| GET | `/notifications?unread=true&page_key=&type=&page=1&page_size=20` | login | My notifications, newest first |
| GET | `/notifications/unread-count` | login | Bell count + per-page badge counts |
| GET | `/notifications/{id}` | login | One notification |
| PATCH | `/notifications/{id}/read` | login | Mark read (body `{"is_read": false}` marks unread) |
| POST | `/notifications/read-all?page_key=` | login | Mark all (or one page's) read |
| DELETE | `/notifications/{id}` | login | Delete one |
| DELETE | `/notifications` | login | Clear all read ones |
| POST | `/notifications` | super_admin / admin | Send an announcement to staff |

```json
GET /notifications/unread-count
{ "count": 3, "by_page": { "public_enquiry": 2, "surveys_campaigns": 1 } }

GET /notifications
{ "items": [ { "id": "NTF-15", "type": "public_enquiry", "title": "New enquiry from Ravi (Palur, Kandukur)",
               "message": "Water Supply: ...", "link": "/dashboard/PublicEnquiryRequests", "page": "public_enquiry",
               "reference_id": "KDK-31", "is_read": false, "read_at": null, "created_at": "..." } ],
  "total": 8, "unread": 3, "page": 1, "page_size": 20, "pages": 1 }

POST /notifications   { "title": "Team meeting at 5 pm", "message": "Office hall", "link": null, "page_key": null }
→ { "success": true, "recipients": 12 }       // page_key limits it to staff who can view that page
```

Created automatically:

| `type` | When | Who gets it | `link` |
|---|---|---|---|
| `public_enquiry` | A citizen submits an enquiry | Staff who can view Public Enquiries | `/dashboard/PublicEnquiryRequests` |
| `war_room_alert` | A survey is escalated (VIP Alert / Grievance Fix) | Staff who can view Surveys (not the agent who raised it) | `/dashboard/Surveys` |
| `announcement` | Admin sends one | Everyone, or staff of `page_key` | as sent |

- Each user sees only their own notifications (someone else's id → `404`).
- Clicking one: `navigate(n.link)`, then `PATCH /notifications/{id}/read`.

---

## 7. Telugu website — `?lang=te` on every public endpoint

Visitors switch language on the frontend as today (`i18n.changeLanguage`, saved in the browser — no login, no API call).
When the site is in Telugu, add `?lang=te` to the public API calls and the **data** comes back in Telugu too.

| Endpoint | Fields that become Telugu with `?lang=te` |
|---|---|
| `GET /public/events?lang=te` | `title`, `venue`, `description`, `chief_guest`, `mandal`, `village` |
| `GET /public/development-works?lang=te` | `name`, `remarks`, `contractor`, `mandal`, `village` |
| `GET /public/media?lang=te` | `title` (all groups); `description` (press meets, videos) |
| `GET /public/mandals?lang=te` | `name` |
| `GET /public/villages?lang=te` | `name`, `mandal` |
| `GET /public/voter-lookup/{epic}?lang=te` | `mandal`, `village`, `mandal_name`, `village_name` |
| `GET /public/settings?lang=te` | `profile` (MLA, office address, ...) |

```json
GET /public/events?lang=te
{ "id": "EV-4", "title": "ప్రజా దర్బార్", "title_en": "Praja Darbar", "venue": "టౌన్ హాల్", "venue_en": "Town Hall",
  "mandal": "కందుకూరు", "mandal_en": "Kandukur", "type": "Public Meeting", "status": "Scheduled", ... }
```

- **No Telugu entered yet → English is returned**, never a blank.
- The English value is always kept in `<field>_en`.
- `status`, `type`, `category`, ids, dates and URLs **stay English** so filters and colours keep working — translate their labels with the i18n files.
- Filters accept Telugu names too: `/public/development-works?mandal=కందుకూరు`, `/public/villages?mandal_name=కందుకూరు`.
- Forms submitted from the Telugu site (`POST /public/enquiries`, `POST /contact`) can send Telugu mandal/village names; the backend stores the English names.
- Without `lang` (or `lang=en`) every response is exactly as before.

**Dashboard forms — where the Telugu text comes from.** Staff type it when adding/editing; send these next to the English fields:

| Form | New optional fields |
|---|---|
| `POST/PUT /events` | `title_te`, `venue_te`, `description_te`, `chief_guest_te` |
| `POST/PUT /development-works` | `name_te`, `remarks_te` (`contractor_te` already existed) |
| `POST/PUT /media/press-meets` | `title_te`, `description_te` |
| `POST/PUT /media/videos` | `title_te`, `description_te` |
| `POST/PUT /media/albums`, `/media/mp3`, `/media/mp4` | `title_te` |
| Mandals / villages | `name_te` (section 3) |
| Office profile | `profile_te` on `PUT /settings` (existing) |

- Dashboard rows return these `*_te` keys (plus `mandal_te` / `village_te`) so edit forms can show them.
- Only the `*_te` keys you send change: leaving one out keeps it, `""` clears it.

---

## Where to wire them in the frontend

- [ ] `src/api/index.js` `authAPI.login` and `src/components/Login.js` — send `username`; change the input to "Email or mobile number" (`type="text"`).
- [ ] `src/api/index.js` `authAPI.forgotPassword` — send `{ username }`.
- [ ] `src/i18n.js` / public layout — call `GET /public/settings` on load and `i18n.changeLanguage(default_language)` unless the visitor already picked a language.
- [ ] `src/components/Contact.js` — replace hardcoded `MANDAL_DATA` with `/public/mandals` + `/public/villages`.
- [ ] `src/api/geography.js` + `useGeography` — show `name_te` in Telugu mode.
- [ ] `SettingsPage.jsx` — mandal/village add/edit/delete can use the new geography endpoints instead of re-saving all dropdowns.
- [ ] `Surveys.jsx`, `SurveyModals.jsx` — use `positive_pct` / `negative_pct` / `completion_pct` instead of computing.
- [ ] `src/api/index.js` `fileAPI` — add `list`, `get`, `update`, `delete`.
- [ ] `AdminNav.js` bell — poll `GET /notifications/unread-count` (e.g. every 60 s) and open a dropdown from `GET /notifications`.
- [ ] `Sidebar.js` line 258 — replace the hardcoded `1` badge with `by_page.public_enquiry`.
- [ ] Public pages (`PublicEvents.jsx`, `PublicAttainments.jsx`, `PublicMedia.jsx`, `Contact.js`) — switch from mocks to the `/public/*` endpoints and add `lang: i18n.language.startsWith("te") ? "te" : "en"`; refetch when the language changes (`i18n.on("languageChanged", ...)`).
- [ ] Dashboard forms (`AddEventModal.jsx`, `AddDevelopmentWorkModal.jsx`, `MediaModals.jsx`) — add "Title (Telugu)" etc. inputs sending the `*_te` fields.
