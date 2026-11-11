# MNBJYN Election Results – API & Back-end Documentation

**For:** the developers of the polling-unit results app.
**Back-end:** Django 5 (this repository). **API version:** `v1`. **Base path:** `/api/v1/`

The back-end does three jobs:

1. **Collects** polling-unit (PU) result sheets from agents in the field (the app you are building).
2. **Reviews** them (supervisors verify / dispute / reject).
3. **Serves** the live numbers to the website's *Situation Room*, which can be switched between a **simulation** and **live** results.

```
   Field app (agents)        Supervisor app / web        Administrator
          │                          │                         │
          └──────────────┬───────────┴─────────────────────────┘
                         ▼
                /api/v1/…  (this back-end)  ──►  database (Postgres)
                         │
                         ▼
        Situation Room on the home page  (reads /api/v1/public/…)
```

---

## 1. Quick start for app developers

1. Get the app's **base URL** and your registered agent account's phone + temporary PIN. An administrator must create the agent account, but does not need to assign your polling unit.
2. `POST /api/v1/auth/login/` → keep the `token`.
3. The first login has `must_change_pin: true` → `POST /api/v1/auth/change-pin/`.
4. `GET /api/v1/election/current/` → candidates (build the result form from this; **never hard-code candidates**).
5. `GET /api/v1/agent/assignments/` → your assigned polling units. If `can_self_assign` is true, show the returned guidance and let the agent choose a unit.
6. `GET /api/v1/agent/available-polling-units/` → browse unassigned active units; `POST /api/v1/agent/claim-assignment/` claims one. An agent may self-assign one unit; no administrator approval is needed. Claims cannot be changed by the agent.
7. `POST /api/v1/results/` → submit a result (generate a UUID `submission_id` on the phone first).
8. Optionally `POST /api/v1/results/{id}/sheet/` → upload a photo of the signed result sheet.

An OpenAPI 3 description is served at **`/api/v1/openapi.json`** (and a copy is in `docs/openapi.json`). Import it into Postman / Insomnia / Swagger UI, or use it to generate a client.

```bash
BASE=https://your-domain
curl -s $BASE/api/v1/auth/login/ -H 'Content-Type: application/json' \
     -d '{"phone":"08012345678","pin":"493021","device_name":"Tecno Spark 10"}'
curl -s $BASE/api/v1/agent/assignments/ -H "Authorization: Bearer $TOKEN"
```

---

## 2. Conventions

| Topic | Rule |
|---|---|
| Format | JSON in and out, UTF-8. Send `Content-Type: application/json`. Photos and CSV use `multipart/form-data`. |
| Auth | `Authorization: Bearer <token>` on every endpoint except those marked **public**. |
| Trailing slash | Both `/results/` and `/results` work. Use the slash form. |
| Times | ISO-8601. The server returns UTC (`…+00:00` or `…Z`). Send `client_time` with your offset (e.g. `+01:00`). |
| Numbers | Vote counts are **whole numbers ≥ 0** (strings of digits are tolerated; floats with decimals, booleans and negatives are rejected). |
| IDs | Candidates are identified by their numeric `id`. Polling units by their **code** (`20/21/03/007`). In URLs you may write the code with dashes (`20-21-03-007`). |
| Pagination | `?page=1&page_size=50` (max 200). Responses carry `count`, `page`, `page_size`, `pages`. |
| Caching | Authenticated responses are `Cache-Control: no-store`. Public responses are cached for a few seconds. |

### Polling-unit codes

`<state>/<LGA>/<ward>/<PU>` → `20/21/03/007` = Kano (20) / LGA 21 (Kano Municipal) / ward 03 / PU 007.
LGA code positions come from `core/lga_data.py`. The initial 484 wards are seeded
from `core/kano_lgas.json`; the database catalog is editable from `/admin/`.
Ward `index` values remain stable for polling-unit codes, even when ward names or
display order change. Polling units are imported separately; always use the `code`
the API returns, never build codes yourself.

### Error format

Every error has the same shape:

```json
{ "error": { "code": "validation_failed",
             "message": "Some fields are invalid.",
             "fields": { "votes": "Missing candidate id(s): 4. Send 0 for no votes." } } }
```

| HTTP | `code` | Meaning / what the app should do |
|---|---|---|
| 400 | `invalid_json` | Body is not a JSON object. Bug in the app. |
| 401 | `not_authenticated`, `invalid_token` | No/expired/revoked token → show the login screen. |
| 401 | `invalid_credentials` | Wrong phone or PIN (deliberately vague). |
| 403 | `forbidden` | Role not allowed. |
| 403 | `not_assigned` | Agent is not assigned to that polling unit. |
| 403 | `pin_change_required` | Call `POST /auth/change-pin/` first. |
| 404 | `not_found`, `polling_unit_not_found` | Unknown resource (also returned for results that belong to someone else). |
| 409 | `no_active_election` | No election is open yet. |
| 409 | `already_verified` | The PU's result is verified/locked; a supervisor must reject it before it can be corrected. |
| 409 | `submission_id_reused` | Same `submission_id` with different figures. Generate a new UUID. |
| 409 | `polling_unit_claimed` | Another agent already claimed the selected polling unit; choose an available unit. |
| 409 | `assignment_limit_reached` | This agent already has one assignment; contact an administrator to change it. |
| 409 | `conflict` | Two writes collided. **Retry the same request**. |
| 413 | `payload_too_large` | JSON > 1 MB or photo > 4 MB. Compress the photo. |
| 415 | `unsupported_media_type` | Missing `Content-Type: application/json`. |
| 422 | `validation_failed` | Field errors in `error.fields`. Fix and resend. |
| 422 | `anomalies_detected` | Figures look odd (see §5.2). Ask the agent to confirm. |
| 429 | `account_locked` | Too many wrong PINs. Wait `retry_after_seconds` or ask the administrator. |
| 429 | `rate_limited` | Slow down; honour `Retry-After`. |
| 5xx | `server_error` | Retry with back-off. Safe for `POST /results/` because of idempotency. |

---

## 3. Roles & security model

| Role | Who | Can |
|---|---|---|
| `agent` | Polling-unit agent | Log in, self-assign one available active PU if unassigned, read assignments, **submit** results for assigned PUs, upload sheet photos, read own submissions. |
| `supervisor` | Ward / LGA collation officer | Read results in their area (whole state, or one LGA via `lga_scope`), **verify / dispute / reject**, see summaries. Cannot submit. |
| `admin` | Results administrator | Everything above for the whole state, plus manage agents, assignments, polling units, elections, the Situation Room switch and read the audit log. |

Security measures built in:

* **Tokens**: random 256-bit bearer tokens; only a SHA-256 hash is stored. Valid 72 h (configurable), max 5 live devices per user, revocable (logout, PIN reset, deactivation).
* **PINs**: 6 digits, stored with Django's password hasher (PBKDF2). Temporary PIN issued by an admin **must be changed at first login**. Simple PINs (`111111`, `123456`…) are refused.
* **Brute-force protection**: 5 wrong PINs lock the account for 15 min (works across servers because it is stored in the database); per-IP and per-user rate limits.
* **Least privilege**: role checks on every endpoint; agents only reach their own PUs and their own submissions (others return 404, not 403, to avoid probing). Self-assignment is limited to one active PU that no agent has claimed; there is no agent-facing release or reassignment endpoint.
* **Integrity**: submissions are *never edited*. A correction is a new row; the old one becomes `superseded`. Each carries a SHA-256 of its figures. Verified results are locked.
* **Idempotency**: a client-generated `submission_id` makes retries safe.
* **Audit log**: logins (incl. failures), submissions, reviews and every admin action are recorded with IP and device.
* **Privacy**: the public Situation Room shows an agent only as "Aminu M."; result-sheet photos are private (only the owner, supervisors in scope and admins can fetch them).
* **Transport**: always use HTTPS. In production the back-end sets secure cookies, `nosniff`, `no-referrer`, and answers CORS only for allow-listed origins (native apps are unaffected by CORS).

> **App security checklist:** store the token in the Android Keystore / iOS Keychain (not plain preferences); never log tokens or PINs; pin the production host; send `device_name`; on `401` wipe the token and go to login; don't keep unsent results in plain text longer than needed.

---

## 4. Concepts

**Election & candidates.** One election is *current* (`GET /election/current/`). Its candidates have a numeric `id`, `name`, `short_name`, `color`, `order`. A result must contain a vote count for **every** candidate id (use `0` for none).

**Result figures** (mirror the INEC polling-unit result sheet):

| Field | Meaning |
|---|---|
| `registered_voters` | Registered voters at the PU. Optional if the back-end already has it for that PU. |
| `accredited_voters` | Voters accredited on the day. |
| `rejected_votes` | Rejected ballots. |
| `votes` | `{ "<candidate id>": count, … }` for **all** candidates. |
| `valid_votes` | *Optional cross-check.* The server computes it as the sum of `votes`; if you send it and it differs you get a 422. |

**Result status lifecycle**

```
 submitted ──verify──► verified (locked)
     │  └──dispute──► disputed          Agent re-submits → old row becomes `superseded`
 flagged  (agent confirmed odd figures)   Supervisor `reject` → agent may re-submit
     └──verify/dispute/reject by supervisor
```

*What the Situation Room shows:* `submitted` and `verified` results (or only `verified` if the administrator turns off "show results before verification"). `flagged`, `disputed`, `rejected`, `superseded` are held back.

---

## 5. Building the app: recommended flows

### 5.1 Offline-first submission

Networks on election day are unreliable. Recommended pattern:

1. When the agent taps **Submit**, create the payload **with a new UUID v4 `submission_id`**, save it in a local queue (encrypted storage), mark *pending*.
2. Send `POST /results/`. On **201 or 200 (duplicate)** → mark *sent*. On network error / 5xx / 409 `conflict` / 429 → keep in queue and **retry the identical payload** with exponential back-off (2 s → 4 s → … max 60 s).
3. On **4xx other than the above** → don't retry blindly; show the error to the agent so they can fix the figures, then create a **new** `submission_id`.
4. When connectivity returns after a long gap you may send up to 20 queued items at once with `POST /results/batch/` (each item is judged separately, see below).
5. Show the agent a status per PU from `GET /agent/assignments/` (`result.status`). If `can_self_assign` is true, display the response's `message`, let them browse available units and claim one without admin assignment.

Retrying the same `submission_id` + same figures is always safe; you'll get the original record back with `"duplicate": true`.

### 5.2 Anomaly confirmation (important UX)

Some figures are *possible but suspicious*. The API refuses them the first time with `422 anomalies_detected`:

```json
{ "error": { "code": "anomalies_detected",
  "message": "These figures look unusual. Re-check the result sheet; …",
  "anomalies": [ { "code": "votes_exceed_accredited",
                   "message": "Valid + rejected votes are more than the number of accredited voters." } ] } }
```

Possible codes: `accredited_exceeds_registered`, `votes_exceed_accredited`, `registered_differs_from_register`, `high_rejected_votes`, `location_far_from_polling_unit`.
Show the messages, let the agent re-check the sheet. If the sheet really says so, resend the **same payload with `"acknowledge_anomalies": true`**. It is stored with status `flagged` and a supervisor reviews it.

### 5.3 Result-sheet photo

After a successful submit, `POST /results/{id}/sheet/` as `multipart/form-data` with field `sheet` (JPEG/PNG/WEBP). **Max 4 MB** (the hosting platform rejects bigger bodies): downscale to ~1600 px on the long edge, JPEG quality ~80, before uploading (typically 300–800 KB). Uploading again replaces the photo (allowed until the result is verified).

### 5.4 GPS (optional but recommended)

Send `latitude` and `longitude` (together). If the polling unit has coordinates on file and the phone is >1.5 km away, the result raises the `location_far_from_polling_unit` anomaly.

---

## 6. Endpoint reference

Legend: 🌐 public · 🔑 any logged-in user · **A** agent · **S** supervisor · **AD** admin.

### 6.1 System & public data (🌐)

| Method & path | Purpose |
|---|---|
| `GET /health/` | Liveness check. |
| `GET /openapi.json` | OpenAPI 3 description. |
| `GET /public/config/` | `mode` (`simulation`/`live`), `refresh_seconds`, election + candidates. **This is what the Situation Room reads to know which mode to show.** |
| `GET /public/structure/` | All 44 LGAs → database wards → polling units in one compact response. PU entries are arrays `[number, code, name, registered_voters]`. |
| `GET /public/results/?since=<cursor>` | Public results. First call without `since` returns everything (`full: true`); then pass back the returned `cursor` to get **only changes**. Row: `{pu, registered, accredited, rejected, valid, votes:[…in candidate order…], by, at, status}`. `withdrawn` lists PU codes whose result was removed (disputed/rejected). `public_count` is the server's total, used by clients to self-check. |
| `GET /public/summary/?lga=kano_municipal&ward=3` | Totals and per-candidate percentages for the state, an LGA or a ward. |
| `GET /public/lgas/` · `/public/lgas/{lga}/wards/` · `/public/lgas/{lga}/wards/{ward_index}/polling-units/` | Directory browsing. `lga` is a Kano LGA key such as `kano_municipal`, `dawaki_kudu`, or `tudun_wada`. |

The public ward directory is backed by the Django admin's **Wards** catalog. Ward
names and display order may be edited there; the stable `ward_index` used in
polling-unit codes is not changed by display reordering. Adding or removing wards
is reflected by the directory and Situation Room after the database migration.

### 6.2 Authentication

**`POST /auth/login/`** (🌐, 10 requests/min/IP)
```json
{ "phone": "08012345678", "pin": "493021", "device_name": "Tecno Spark 10" }
```
→ `200`
```json
{ "token": "mnbjyn_…", "token_type": "Bearer", "expires_at": "2027-02-27T06:00:00+00:00",
  "agent": { "id": 7, "full_name": "Aminu Musa", "role": "agent", "must_change_pin": true, "assigned_polling_units": 2, "…": "…" } }
```
Phone numbers are normalised (`+234 801 234 5678` = `08012345678`).

**`POST /auth/change-pin/`** 🔑 `{ "current_pin": "…", "new_pin": "718305" }` → `{ "ok": true }`. Signs out the user's other devices.
**`POST /auth/logout/`** 🔑 → revokes the current token.
**`GET /auth/me/`** 🔑 → `{ agent, token_expires_at }`.

### 6.3 App endpoints

**`GET /election/current/`** 🔑 → `{ "election": { id, name, slug, election_date, candidates:[{id,name,short_name,color,order}] } }`

**`GET /agent/assignments/`** **A** → the agent's polling units:
```json
{ "election": { "…": "…" },
  "can_self_assign": false, "message": "",
  "polling_units": [ { "code": "20/21/03/007", "number": 7, "name": "Polling Unit 007",
      "lga": "kano_municipal", "lga_name": "Kano Municipal", "ward_index": 2, "ward_name": "Gandun Albasa",
      "registered_voters": 612, "latitude": null, "longitude": null,
      "result": { "id": 118, "status": "submitted", "submitted_at": "…", "has_sheet": false } } ] }
```
`result` is `null` until a result exists.

When `polling_units` is empty, the response sets `can_self_assign: true` and explains that the agent can choose an assignment without contacting an administrator.

**`GET /agent/available-polling-units/`** **A** (`?lga=kano_municipal&ward=2&q=school&page=1`) returns active, unassigned polling units. It is empty after an agent has claimed a unit.

**`POST /agent/claim-assignment/`** **A** claims one unit:
```json
{ "polling_unit_code": "20/21/03/007" }
```
→ `201` `{ "polling_unit": { ... }, "already_claimed": false }`. Repeating a claim for the same unit is safe and returns `200`; claiming a unit taken by another agent returns `409 polling_unit_claimed`. An agent can claim only one unit, and must ask an administrator to change or remove an assignment.

**`POST /results/`** **A**
```json
{ "submission_id": "3f2b8c1e-6a4d-4f55-9d36-2b1f0c7a9e10",
  "polling_unit_code": "20/21/03/007",
  "registered_voters": 612,
  "accredited_voters": 301,
  "rejected_votes": 4,
  "valid_votes": 297,
  "votes": { "1": 120, "2": 98, "3": 51, "4": 28 },
  "latitude": 10.3158, "longitude": 9.8442,
  "client_time": "2027-02-25T15:01:50+01:00",
  "acknowledge_anomalies": false }
```
→ `201` `{ "duplicate": false, "submission": { id, submission_id, status, valid_votes, flags, has_sheet, … } }`
→ `200` with `"duplicate": true` for a replay.
Rules: all candidate ids required; `valid_votes` (if sent) must equal the sum; `votes`, `accredited_voters`, `rejected_votes` are integers 0–20000. A new submission for a PU that already has an unverified result **replaces** it (old → `superseded`).

**`POST /results/batch/`** **A** `{ "items": [ <result>, … ] }` (1–20). Always `200`; each entry: `{ index, ok, duplicate?, submission? , error? }`. `accepted` = number OK.

**`GET /results/mine/`** **A** (`?history=1` includes replaced rows) · **`GET /results/{id}/`** 🔑 (own / in scope).

**`POST /results/{id}/sheet/`** **A/AD** multipart `sheet` · **`GET /results/{id}/sheet/`** 🔑 returns the image (owner, supervisors in scope, admins).

### 6.4 Supervision (**S**, **AD**)

| Endpoint | Notes |
|---|---|
| `GET /results/?lga=&ward=&status=&history=1` | Paginated list in the caller's area (current election). |
| `POST /results/{id}/review/` | `{ "action": "verify" \| "dispute" \| "reject", "note": "…" }`. `note` (≥5 chars) is required for dispute/reject. `verify` locks the result. Reject also unlocks a verified result so the agent can resubmit. |
| `GET /results/summary/?lga=&ward=` | Totals **including unverified** results plus `by_status` counts. |

### 6.5 Administration (**AD**)

| Endpoint | Purpose |
|---|---|
| `GET /admin/agents/?role=&q=` | List users. |
| `POST /admin/agents/` | Create user: `{ full_name, phone, role, lga_scope?, polling_unit_codes? / ward? / lga? }` → response includes **`temporary_pin` (shown once)**. |
| `GET /admin/agents/{id}/` · `PATCH` | Details (with assigned PUs) / edit `full_name, phone, role, lga_scope, is_active`. Deactivating signs the user out. |
| `POST /admin/agents/{id}/reset-pin/` | New temporary PIN; unlocks; signs out everywhere. |
| `POST /admin/agents/{id}/revoke-tokens/` | Sign out everywhere. |
| `POST /admin/agents/{id}/assignments/` | `{ "mode": "add"\|"remove"\|"replace", "polling_unit_codes": [...], "ward": {"lga":"kano_municipal","ward_index":3}, "lga": "kano_municipal" }` |
| `GET /admin/polling-units/?lga=&ward=&q=` · `PATCH /admin/polling-units/{code}/` | Browse / correct name, `registered_voters`, coordinates, `is_active`. |
| `POST /admin/polling-units/import/` | CSV upload (see §7.3). |
| `GET/POST /admin/elections/` · `PATCH /admin/elections/{id}/` | Create elections with candidates; set `is_current`. Candidates are locked once results exist. |
| `GET /admin/situation-room/` | Current mode, **go-live warnings**, counters. |
| `PATCH /admin/situation-room/` | `{ "mode": "live" \| "simulation", "publish_unverified": true, "refresh_seconds": 10 }`. Refuses `live` if there is no current election or no polling units. |
| `GET /admin/audit/?action=&actor=` | Audit log. |

---

## 7. Back-end operations (for whoever deploys it)

### 7.1 Environment variables

| Variable | Purpose |
|---|---|
| `DJANGO_SECRET_KEY` | **Required in production.** Long random string. |
| `DJANGO_DEBUG` | `0` in production. |
| `DATABASE_URL` | **Postgres URL** (Neon, Supabase…). Without it data is stored in temporary SQLite and is lost. |
| `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_ORIGINS` | Your domain(s). |
| `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_PASSWORD` | Override the default Django super-user (see warning below). |
| `API_TOKEN_TTL_HOURS` | Token life, default `72`. |
| `API_LOGIN_MAX_FAILS`, `API_LOGIN_LOCK_MINUTES` | Lockout policy, default `5` / `15`. |
| `API_CORS_ORIGINS` | Comma-separated browser origins allowed to call private endpoints (e.g. a web version of the app). Not needed for native apps. |
| `API_TRUST_PROXY` | `1` behind a proxy (default on Vercel) so rate limits and the audit log see the real client IP. |
| `API_MAX_SHEET_BYTES` | Photo size limit (default 4,000,000; Vercel rejects > 4.5 MB bodies). |

### 7.2 First-time setup

```bash
python manage.py migrate                      # creates tables, a starter election and the Situation Room settings
python manage.py seed_polling_units           # PLACEHOLDER polling units (8–15 per ward) so you can test
python manage.py create_agent --name "Admin" --phone 08000000000 --role admin    # prints a temporary PIN
python manage.py check_live_ready             # go-live checklist
python manage.py test core                    # run the automated tests
```
Then in `/admin/`: **Elections** (set the real candidates), **Result agents** (create agents and assign polling units), **Situation Room settings** (switch).

### 7.3 Loading the official polling units

Placeholder units have no names and no voter counts. Load the official INEC list from a CSV:

```csv
lga,ward,pu_number,name,registered_voters,latitude,longitude,code
Kano Municipal,Gandun Albasa,1,"Primary School, Gandun Albasa",612,12.0,8.5,20/21/03/001
```
* `lga`, `ward`, `pu_number` are required. Ward names must match the admin-managed catalog (case, spaces and quotes are ignored). `code` is optional (derived if absent).
* `python manage.py import_polling_units file.csv --dry-run` checks the file; without `--dry-run` it imports. Add `--replace` to remove placeholder units not in the file (units that already have results are deactivated, never deleted).
* Or `POST /api/v1/admin/polling-units/import/` (max 4 MB per upload; split big files by LGA).
* The import is all-or-nothing: if any row is wrong nothing is imported and the problems are listed.

### 7.4 Going live

1. `python manage.py check_live_ready` shows **critical** items to fix (also shown under *Situation Room settings* and in `GET /admin/situation-room/`).
2. Switch: `/admin/` → *Situation Room settings* → mode **Live**, or `PATCH /api/v1/admin/situation-room/ {"mode":"live"}`.
3. Open pages notice the change within ~30 s; new visitors see live immediately. In live mode **simulated numbers are never displayed**: if the API is unreachable the page says so and keeps the last real data.
4. To go back, set the mode to **Simulation**.

### 7.5 ⚠ Security warnings before election day

* The repository contains a **default super-user password in `core/accounts.py`**. Anyone who can read the code can log in to `/admin/` (which can switch the Situation Room and see all results). **Set `DJANGO_SUPERUSER_PASSWORD` and change the password** (or remove the default) before going live.
* Set a real `DJANGO_SECRET_KEY` (otherwise a predictable fallback key is used on Vercel).
* Use Postgres. Keep a database backup schedule during the election.
* Serverless hosting (Vercel) limits: request body ≤ 4.5 MB; the default in-memory rate limiter is per server instance (strong enough against casual abuse; configure a shared cache such as Redis if you need exact global limits).
* The API is open to the internet: HTTPS only, and distribute temporary PINs privately.

### 7.6 Code map

```
core/api/
  urls.py          route table
  base.py          errors, JSON helpers, rate limiting, token auth, endpoint decorator
  validators.py    all input validation + anomaly rules (pure Python, unit-testable)
  services.py      business logic: login, submit_result, review, public aggregation, go-live checks
  views_public.py  public endpoints          views_agent.py  app + supervisor endpoints
  views_admin.py   administrator endpoints   pu_import.py     CSV import / placeholder generator
  middleware.py    CORS + security headers   openapi.py       OpenAPI description
core/models.py     Election, Candidate, PollingUnit, ResultAgent, ApiToken, ResultSubmission, AuditLog, SituationRoomConfig
core/static/core/js/situation.js   Situation Room (simulation + live)
core/tests_api.py  automated tests
```

---

## 8. How the Situation Room uses the API

* On load it reads the mode injected into the page. In **simulation** it generates sample data in the browser (and checks `/public/config/` every 30 s in case the administrator switches to live).
* In **live** mode it loads `/public/config/` (candidates) and `/public/structure/` (LGAs, wards, PUs), then polls `/public/results/?since=<cursor>` every `refresh_seconds` (default 10 s), applying only changes. Totals for the state, each LGA, ward and polling unit are computed from the per-PU results, so the numbers always add up.
* If its count of reported PUs ever differs from the server's `public_count`, it downloads everything again.
* Visitors can drill down **State → LGA → Ward → Polling unit** in both modes.

---

## 9. Change log

* **v1.0** – initial release: authentication, assignments, result submission (single and batch), idempotency, anomaly confirmation, sheet photos, supervision workflow, admin management, polling-unit import, Situation Room live mode, audit log.
