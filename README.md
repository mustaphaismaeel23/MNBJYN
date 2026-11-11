# MNBJYN Kano State Election Results System

Django 5 backend and web-based Kano election results dashboard with administrator-managed
agents, polling-unit assignments, elections, submissions and reviews. Member registration
and the member workspace are disabled. This repository does not currently contain a Flutter
project or a built Android APK.

## Quick start

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
export DJANGO_SUPERUSER_PASSWORD="replace-with-a-strong-password"
python manage.py migrate
# The migration creates the initial super-user when the password is set.
python manage.py runserver
```

On Windows PowerShell, set the administrator password before migrating:

```powershell
$env:DJANGO_SUPERUSER_PASSWORD = "replace-with-a-strong-password"
python manage.py migrate
```

* Website: http://127.0.0.1:8000/
* Live results dashboard: http://127.0.0.1:8000/#situation-room
* Admin: http://127.0.0.1:8000/admin/

## Pages

| URL | What it is |
|-----|-----------|
| `/` | Kano election results dashboard and public site |
| `/admin/` | Admin only |

## Admin (`/admin/`)

* **Election operations dashboard**: real polling-unit coverage by LGA, agent assignments,
  submissions awaiting review, approved and rejected result totals.
* **Site settings**: upload a portrait of Malam Nasiru Bala Ja'oji (~4:5 works best) and edit its caption.
  Until a photo is uploaded, a neutral MNBJYN brand graphic is shown.
* **Gallery photos**: add photos, captions, ordering, publish/unpublish. Five supplied
  photos of Malam Nasiru Bala Ja'oji appear by default; published gallery uploads
  replace these defaults.

## Editing the website text

All public copy lives in `core/content.py`.
Edit it there; no template changes needed.

Kano's 44 LGAs and 484 wards are loaded from `core/kano_lgas.json`. Polling units for live
results are imported separately through the admin API or `manage.py import_polling_units`.
The location names are from [mykeels/inec-polling-units](https://github.com/mykeels/inec-polling-units)
and are distributed under the MIT license in `core/INEC-DATA-LICENSE.txt`.

## Production notes

Set these environment variables:

```
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=<long random string>
DJANGO_SUPERUSER_PASSWORD=<strong initial administrator password>
DJANGO_ALLOWED_HOSTS=yourdomain.org,www.yourdomain.org
DJANGO_CSRF_ORIGINS=https://yourdomain.org,https://www.yourdomain.org
```

The initial super-user is created only when `DJANGO_SUPERUSER_PASSWORD` is set
when migrations run. To create or reset it later, set the same variable and run
`python manage.py ensure_superuser`.

Then:

```bash
python manage.py collectstatic --noinput
gunicorn config.wsgi
```

Static files are served by WhiteNoise. Uploaded photos live in `media/`; serve that
folder from your web server or object storage in production. SQLite is the default
database; switch `DATABASES` in `config/settings.py` to PostgreSQL for heavier use.

## Project layout

```
manage.py
config/            settings, urls, wsgi/asgi
core/
  models.py        Registration, SiteSettings, GalleryImage
  forms.py         registration form (validation, duplicate-phone check, honeypot)
  views.py         public home and media
  content.py       all website text
  admin.py         admin configuration (+ CSV export, bulk actions)
  admin_site.py    dashboard statistics
  templates/       core/*.html and admin/index.html
  static/core/     css + js
```


The staff-only Django admin at `/admin/` provides election operations shortcuts
for elections, polling units, results agents/PINs, result reviews, Situation Room
settings and the audit log, along with live counts for agents, polling units and
results needing review. Manage the ward directory under **Wards**: rename wards,
add wards and adjust their display order. Ward codes keep their existing index;
changing display order does not renumber polling units. A ward with polling units
cannot be deleted. Polling units can be searched and edited from **Polling units**,
including their ward, number, name, voter count and active status. When adding a unit,
select its ward and number; its polling-unit code is generated automatically.

## Visual design and photography

The public-site styling keeps the MNBJYN red (`#DA0010`), white and black palette,
with lighter typography, more restrained heading sizes, softer corners and more
space. A community photo selected from the supplied root-folder images is the
default hero; uploaded hero media configured in Site Settings still takes
precedence. Selected supplied photographs also appear in the gallery when no
gallery entries have been uploaded. Add and publish gallery entries through
Django admin to replace the curated fallback gallery.

## Design system (October 2026)

The public dashboard uses restrained typography, generous spacing, clear content hierarchy, quiet surfaces and thin dividers. MNBJYN's red remains the primary accent, supported by white, charcoal and cool neutral backgrounds.

- **Typography:** Manrope for display/headings and DM Sans for body/UI. These are close-fit substitutions, not fonts verified from Elasto.ng's computed styles.
- **Palette:** MNBJYN red `#D7192D`, charcoal `#15171C`, white `#FFFFFF`, cool wash `#F6F7F8`, and divider `#E4E6EA`. These values are project design tokens, not a claim about Elasto's palette.
- **Layout:** a centered content width around 1180px, responsive gutters, large section spacing, two-column editorial layouts where content allows, and single-column mobile forms.
- **Components:** consistent button geometry, accessible focus outlines, restrained borders/shadows, outlined registration controls, and calmer cards for objectives, leadership, and gallery items.
- **Motion:** existing scroll-reveal and situation-room effects remain, with reduced-motion support preserved.

The live reference's exact CSS, computed typography and viewport behaviour could not be extracted in this environment. The result is an evidence-informed adaptation rather than a pixel-identical reproduction.

## Deploying on Vercel

Files that make this work: `vercel.json` (routes every URL to Django), `config/wsgi.py`
(exposes `app`, auto-runs migrations), `.vercelignore`, `.python-version`, `requirements.txt`.

Set these in **Vercel → Project → Settings → Environment Variables**, then redeploy:

| Variable | Value |
|---|---|
| `DJANGO_SECRET_KEY` | a long random string (required for security) |
| `DATABASE_URL` | Postgres URL (Neon / Supabase / Vercel Postgres). Without it, data lives in temporary `/tmp` SQLite and **is lost** |
| `DJANGO_ALLOWED_HOSTS` | (optional) add your custom domain, e.g. `ssbyn.org,www.ssbyn.org` |
| `DJANGO_CSRF_ORIGINS` | (optional) `https://ssbyn.org,https://www.ssbyn.org` |

For Supabase on Vercel, use the project's **Transaction pooler** connection string
from **Supabase → Connect** (not the direct `db.<project-ref>.supabase.co` host,
which may resolve only to IPv6). Copy the full URL into Vercel's `DATABASE_URL`
value; do not put it in `settings.py` or include quotes or `DATABASE_URL=` in the
value. The Vercel database configuration requires SSL and disables server-side
cursors/prepared statements for transaction-pooler compatibility.

`*.vercel.app` hosts are allowed automatically. Create your admin login once, from your
own computer, with `DATABASE_URL` pointed at the same Postgres database:
`python manage.py createsuperuser`.

Note: Vercel's disk is not persistent, so photos uploaded in the admin (hero / gallery)
will not survive. Use object storage (e.g. Cloudinary / S3) for uploads.


## October 2026 update

* **Super-user:** `python manage.py migrate` creates the admin account **Devmusteey** when
  `DJANGO_SUPERUSER_PASSWORD` is set. It works at `/admin/`.
  Override with `DJANGO_SUPERUSER_USERNAME` / `DJANGO_SUPERUSER_PASSWORD`; repair or reset any time with
  `python manage.py ensure_superuser`. (On Vercel the migration runs automatically on cold start.)
* **All 44 LGAs:** `core/kano_lgas.json` provides the initial LGA and ward catalog; the database-backed
  ward list is editable in `/admin/`. Ward code indexes stay fixed when names or display order change.
* **Home page:** the LGA box is a dropdown on the same row as 2026 and 2027. Choosing an LGA reveals
  its ward dropdown, and the chosen LGA and ward are shown together.
* **Situation Room:** live results only, with statewide totals and LGA, ward and polling-unit selectors.
  When no real results are available it shows an empty state; it never generates sample numbers.

## Update: photos, executives and team

* **Uploads now persist:** photos uploaded in `/admin` (hero, gallery, executives, team) are stored in the
  database (`core/storage.py`) and served from `/media/...`, so they work on Vercel. Big photos are resized
  automatically. Login sessions use a signed cookie, which fixes being logged out after saving.
  **Set `DATABASE_URL` (Postgres) and `DJANGO_SECRET_KEY` on Vercel** - without a persistent database
  everything you add in `/admin` is temporary.
* **Executives:** `/admin` > Executives - name, sub-name (title), photo, order, show/hide. Shown in "Our executives".
* **Team members:** `/admin` > Team members - same fields, maximum of 5 (delete one to add another).
* The LGA / ward dropdown sits under the hero image again.

## Make /admin changes permanent (Vercel)

If something you add in `/admin` (team member, hero photo...) does not show on the website, the site is
running on Vercel's temporary database. Each Vercel server instance has its own empty copy, so what you
save in one is invisible to another. The admin shows a red warning when this is the case. Fix:

1. Create a free Postgres database at https://neon.tech (or Supabase) and copy its connection string. For Supabase on Vercel, use its Transaction pooler URL.
2. Vercel -> Project -> Settings -> Environment Variables: add `DATABASE_URL` = that string, and
   `DJANGO_SECRET_KEY` = any long random text. Apply to Production.
3. Redeploy. Migrations run automatically and the `Devmusteey` super-user is created again.
4. Sign in at `/admin/` and add your photos/people again; they now persist and show instantly.

Pages are also sent with `Cache-Control: no-store`, so browsers/CDNs never show a stale copy.


## Election-day results API and live Situation Room (new)

* **Situation Room:** drills down **Kano State > LGA > Ward > Polling unit**. It displays real results only.
* **REST API** under `/api/v1/` for the results app: login (phone + PIN, bearer tokens), assignments,
  result submission (single, batch, idempotent, with anomaly confirmation), result-sheet photos,
  supervisor review, admin management, polling-unit import, audit log.
  **Full documentation for the app developers: [`docs/API.md`](docs/API.md)** and [`docs/openapi.json`](docs/openapi.json)
  (also served at `/api/v1/openapi.json`).

### Results-app agent accounts and polling-unit assignments

The results app uses **results-agent accounts** (`ResultAgent`), which are separate from Django
website accounts. A Django staff or superuser login for `/admin/` does not automatically let that
person sign in to the Android app; create a results agent with the `agent` role for each app user.

1. Import or add the polling units and make sure the units agents should report are active. Create
   the election and its candidates, then mark the election as current.
2. Create an agent in `/admin/` → **Result agents** → **Add**, using the agent's name and phone,
   role `agent`, then select the local government, ward, and polling unit from the dropdowns.
   The selected polling unit is assigned when the agent is saved. A temporary PIN is shown once;
   give it to the agent securely. The agent must change it at first sign-in. Alternatively, create
   an account from the command line:

   ```bash
   python manage.py create_agent --name "Agent Name" --phone 08012345678 --role agent
   ```

3. If an agent needs a different polling unit, an administrator must replace the assignment in
   `/admin/`. Agents cannot claim or alter assignments.

An agent account must be active and have the `agent` role to use these endpoints. See
[`docs/API.md`](docs/API.md) for request/response details and error codes.

* **Set-up commands**

```bash
python manage.py migrate                    # adds the new tables + a starter election
python manage.py seed_polling_units         # PLACEHOLDER polling units for testing only
python manage.py import_polling_units official.csv --replace   # the real INEC list
python manage.py create_agent --name "Admin" --phone 08000000000 --role admin
python manage.py check_live_ready           # go-live checklist
python manage.py test core                  # automated tests
```

* **Before election day:** change the default super-user password in `core/accounts.py` (set
  `DJANGO_SUPERUSER_PASSWORD`), set `DJANGO_SECRET_KEY` and `DATABASE_URL` (Postgres). See `docs/API.md` section 7.
