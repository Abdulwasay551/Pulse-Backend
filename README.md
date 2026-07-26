# EvoHR Backend

Django backend for **EvoHR** — expanding from a recruitment CRM/ATS into a full HCM/ERP suite, organized as five product modules (EVO-Recruit, EVO-People Management, EVO-Talent Management, EVO-Payroll & Benefits, EVO-IT & Asset Management). This service provides:

- A headless **Wagtail CMS** for all public marketing page content (home, pricing, solutions, use cases, who we serve, resources), consumed by the separate [EvoHR frontend](https://github.com/Abdulwasay551/EvoHR-Frontend) over a REST API.
- A **Django admin** themed with [django-unfold](https://github.com/unfoldadmin/django-unfold), kept separate from the CMS admin and reserved for non-CMS data (users, demo requests, and each module app's data).
- A **JWT-based auth API** (`core` app) — register/login/logout, forgot/reset/change password, profile — used by the frontend's real login/signup/dashboard flow.
- The **"Book a Demo"** lead-capture endpoint behind the marketing site's demo-request form.
- **One Django app per product module** (see [Module apps](#module-apps) below) — each module's data model is independent of the others, with `core` holding what's genuinely shared (auth, `ActivityLog`, the `IsOwner` permission).

## Stack

- Django 5.2 + Django REST Framework
- `djangorestframework-simplejwt` (JWT auth, with the refresh token blacklist app enabled)
- Wagtail 7 (CMS + headless API v2)
- django-unfold (Django admin theme)
- SQLite (dev fallback) / Postgres (`DATABASE_URL`, e.g. Neon)

## Getting started

```bash
python -m venv venv
./venv/Scripts/activate   # or source venv/bin/activate on macOS/Linux
pip install -r requirements.txt

cp .env.example .env       # adjust as needed

python manage.py migrate
python manage.py seed_cms            # seeds the page tree, products, and site settings (idempotent, first run only)
python manage.py seed_demo_account   # creates/resets the 'demo' login with sample CRM data (idempotent)
python manage.py createsuperuser
python manage.py runserver
```

## Admin surfaces

| URL | Purpose |
|---|---|
| `/cms/` | Wagtail admin — edit all public page content and the EvoHR product suite snippets |
| `/admin/` | Django admin (Unfold theme) — users, demo requests, and future CRM data |
| `/api/cms/v2/` | Headless REST API consumed by the Next.js frontend (`pages`, `products`, `site-settings`) |
| `/api/health/` | Health check |
| `/api/auth/...` | Auth API (see below) |
| `/api/demo-requests/` | "Book a Demo" form submissions (`POST`, public) |
| `/api/recruit/...` | EVO-Recruit CRUD API (see [Module apps](#module-apps)) |
| `/api/payroll-benefits/...` | EVO-Payroll & Benefits CRUD API (see [Module apps](#module-apps)) |

## Auth API

JWT via `djangorestframework-simplejwt`, split across two tokens so the frontend never has to persist anything sensitive to storage:

- **Access token** — returned in the JSON response body, kept **in-memory only** by the frontend (15 min lifetime). Sent as `Authorization: Bearer <token>`.
- **Refresh token** — set as an **httpOnly, Secure, SameSite** cookie (`evohr_refresh`), never readable by frontend JS (14 day lifetime, rotated + blacklisted on every use). A second, non-httpOnly cookie (`evohr_has_session`) is set alongside it purely as a UX flag ("a session might exist") — it carries no token value.

Login accepts **either a username or an email** in the same `identifier` field (see `core/auth_backends.py::EmailOrUsernameModelBackend`).

| Method & path | Auth required | Purpose |
|---|---|---|
| `POST /api/auth/register/` | — | `{username, email, password, password2}` → creates the account and logs it in |
| `POST /api/auth/login/` | — | `{identifier, password}` → `{access, user}` + sets refresh cookie |
| `POST /api/auth/refresh/` | refresh cookie | → `{access}`, rotates the refresh cookie |
| `POST /api/auth/logout/` | — | Blacklists the refresh token, clears cookies |
| `GET/PATCH /api/auth/me/` | access token | Read/update the current user's profile |
| `POST /api/auth/password/change/` | access token | `{old_password, new_password, new_password2}` — invalidates all existing sessions |
| `POST /api/auth/password/forgot/` | — | `{email}` — always returns a generic response (no account enumeration); emails a reset link to `FRONTEND_URL/reset-password?uid=...&token=...` if the email matches an account |
| `POST /api/auth/password/reset/` | — | `{uid, token, new_password, new_password2}` |

CORS is configured with `CORS_ALLOW_CREDENTIALS = True` so the browser can send/receive the refresh cookie cross-origin — the frontend's origin must be listed in `DJANGO_CORS_ALLOWED_ORIGINS` (below) or these calls fail with a CORS error, not a 401.

## Module apps

Every module API requires the access token and is scoped **per-user** — there's no team/org concept, so a request only ever sees (and can only ever touch) rows where `owner == request.user` (enforced by the shared `core.permissions.IsOwner`). Accessing another user's object by ID returns a plain 404, not a 403 (so IDs don't even leak existence).

| App | Status | Models | API base path |
|---|---|---|---|
| `recruit` | **Real — fully built** | `Client`, `Requisition`, `Candidate`, `OfferLetter`, `BackgroundCheck`, `Onboarding`+`OnboardingTask`, `Offboarding`+`OffboardingTask` | `/api/recruit/` |
| `payroll_benefits` | **Real** (payroll only) | `PayrollRun` | `/api/payroll-benefits/` |
| `people` | **Real** (Employee Records only) | `Employee`, `EmployeeDocument` | `/api/people/` |
| `talent` | Scaffolded, no models yet | — | — |
| `it_assets` | Scaffolded, no models yet | — | — |

`talent`/`it_assets` exist as registered Django apps (in `INSTALLED_APPS`) so they're ready to grow into, but have no models, serializers, views, or URLs yet — their frontend module pages are still all "Coming soon" tiles. `people` has its first sub-module (Employee Records) built; Attendance Management, Employee Engagement, and Workforce Dashboard aren't modeled yet. Add to these apps directly when a module's features start getting built out; don't add unrelated models to `recruit` or `payroll_benefits`.

### EVO-Recruit (`recruit`)

Standard DRF `ModelViewSet` routes (list/create/retrieve/update/partial_update/destroy):

| Path | Model | Notable read-only computed fields |
|---|---|---|
| `/api/recruit/clients/` | `Client` | `open_roles` — count of that client's non-closed requisitions |
| `/api/recruit/requisitions/` | `Requisition` | `client_name`, `candidates_count` |
| `/api/recruit/candidates/` | `Candidate` | `initials`, `client_name`, `requisition_title`; `placed_at` is set automatically the moment `stage` becomes `"Placed"` (and cleared if it moves off it again) |
| `/api/recruit/offer-letters/` | `OfferLetter` | `candidate_detail`; `sent_at`/`signed_at` are set automatically the moment `status` transitions to `"Sent"`/`"Signed"` |
| `/api/recruit/background-checks/` | `BackgroundCheck` | `candidate_detail`; `completed_at` is set automatically the moment `status` transitions to `"Cleared"`/`"Flagged"` |
| `/api/recruit/onboardings/` | `Onboarding` | `candidate_detail`, nested `tasks`, `progress` (% of tasks marked `"Done"`) |
| `/api/recruit/onboarding-tasks/` | `OnboardingTask` | Scoped via `onboarding__owner`, not its own `IsOwner` check — see note below |
| `/api/recruit/offboardings/` | `Offboarding` | `candidate_detail`, nested `tasks`, `progress` |
| `/api/recruit/offboarding-tasks/` | `OffboardingTask` | Scoped via `offboarding__owner`, not its own `IsOwner` check |

Plus:

- `GET /api/recruit/dashboard-summary/` — computes the dashboard's overview stats, pipeline-stage counts, candidate-source breakdown, a 6-month placements trend, and the 6 most recent activity-log entries, all live from the user's own rows (nothing here is stored/cached — see `recruit/views.py::DashboardSummaryView`). "Revenue this month" reads from `payroll_benefits.PayrollRun` — a deliberate cross-app read, since placement-fee revenue is tracked as payroll, not as a Recruit-owned figure.
- `POST /api/recruit/candidates/{id}/screen/` — runs AI resume screening (see below) and returns the updated candidate.
- `GET /api/recruit/clients/export/` and `/candidates/export/` — CSV export of the user's own rows.
- `POST /api/recruit/clients/import/preview/` and `/candidates/import/preview/` (multipart, `file`) — parses an uploaded CSV and returns its columns, all parsed rows, a suggested column→field mapping, and the full set of importable fields.
- `POST /api/recruit/clients/import/commit/` and `/candidates/import/commit/` (JSON, `{columns, rows, mapping}` from the preview step) — validates each row through the resource's normal serializer (proper type coercion + per-row error messages) and creates the valid ones; returns `{created, errors}`.
- `GET /api/recruit/portal/<uuid:token>/` — **public, no auth** (`AllowAny`). The Candidate Portal: looked up by `Candidate.portal_token` (a `UUIDField(unique=True)`, auto-generated, never exposed except as a read-only field on the owner's own candidate detail), not by owner — the candidate isn't a user of this system. Returns `CandidatePortalSerializer`'s narrow field set (name, initials, role, client name, requisition title, stage, applied date) — deliberately excludes email/phone/resume/AI score/anything else internal.

Creating/updating a `Candidate` (stage change) also writes to `core.ActivityLog` via `core.activity.log_activity`, which is what `dashboard-summary` surfaces as "recent activity" — this happens automatically inside the viewset's `perform_create`/`perform_update`, not as a separate call the frontend has to make. The same pattern extends to offer letters, background checks, onboarding, and offboarding.

**AI resume screening** (`recruit/ai_screening.py`) is a heuristic keyword/skill-overlap scorer — it matches words in `Candidate.resume_text` against the linked `Requisition.requirements` (and title) and returns a 0–100 score plus a short explanation of which keywords matched. It's a real, working feature today, not a stub — but it's deliberately built as a drop-in-replaceable placeholder for a future real LLM call, since no LLM vendor account is provisioned for this project yet. Same reasoning for `OfferLetter` (draft → sent → signed/declined is tracked and confirmed manually, not through a real e-signature vendor) and `BackgroundCheck` (status is tracked internally, not through a real vendor like Checkr/Sterling) — both are honest placeholders for integrations that need a vendor account nobody has provisioned.

CSV import is a stateless two-step flow (`core/csv_io.py`) — the preview step does no server-side storage; it hands the *entire* parsed CSV back to the frontend, which round-trips it back unchanged (plus the user-confirmed column mapping) on commit. Capped at 5,000 rows per import.

`Offboarding.rehire_notes` (free-text) backs the frontend's Rehire & Alumni Pool view — a filter over `Offboarding` rows where `rehire_eligible=True`, not a separate model.

### EVO-Payroll & Benefits (`payroll_benefits`)

- `/api/payroll-benefits/payroll-runs/` — standard `ModelViewSet` for `PayrollRun`. Creating a run also logs to `core.ActivityLog` (tone `amber` if status is `"Needs review"`, else `primary`).
- Benefits (enrollment, claims, cost analysis) aren't modeled yet — the frontend module page shows them as placeholder tiles.

### EVO-People Management (`people`)

Employee Records is the first People sub-module built — the rest (Attendance Management, Employee Engagement, Workforce Dashboard) aren't modeled yet.

| Path | Model | Notable read-only computed fields |
|---|---|---|
| `/api/people/employees/` | `Employee` | `initials`, `manager_name`, `direct_reports_count`, nested `documents` |
| `/api/people/employee-documents/` | `EmployeeDocument` | Scoped via `employee__owner`, not its own `IsOwner` check — same reasoning as Recruit's `OnboardingTask` (no `owner` field of its own) |

Plus `GET /api/people/dashboard-summary/` (headcount/active/on-leave/department counts, a department breakdown, and a status breakdown — all live), and the same CSV export/import-preview/import-commit trio as `recruit/clients` and `recruit/candidates`, on `/api/people/employees/`.

`Employee.manager` is a self-referential FK — Organizational Chart (the frontend's `/dashboard/org-chart`) is a derived tree view over it, not a separate model. `Employee.source_candidate` optionally links back to a `recruit.Candidate` for people who came through EVO-Recruit, but isn't required — People also supports employees entered directly. Employee Self-Service and Promotion & Transfer Workflows aren't built yet (would need a real employee-facing auth flow, analogous to Recruit's Candidate Portal reasoning, but bigger in scope since it's read/write not just read-only status).

### The demo account

`python manage.py seed_demo_account` creates (or resets) a `demo` user and fills it with a small realistic dataset across every real module — 8 clients, 6 requisitions, 10 candidates (two with resume text ready to screen), 5 payroll runs, a matching activity log, one sample offer letter, background check, in-progress onboarding (tasks across all 6 categories), in-progress offboarding (tasks across all 3 categories), and 6 employees across 2 departments with a 2-manager org chart (Employee Database/Org Chart/People dashboard all show something real) — so anyone can log in as `demo` / `EvoHRDemo2026!` (or whatever `DEMO_ACCOUNT_PASSWORD` is set to) and see every built feature populated, not just the original candidates/clients/requisitions core. It's a **real account** with real rows, not a special-cased mode — every other signup just starts empty instead. The command (in `core/management/commands/`, since it seeds across `recruit`, `payroll_benefits`, `people`, and `core.ActivityLog`) is idempotent: re-running it wipes and re-creates only that one user's rows, so it's safe to use to reset the demo account after visitors have poked at it.

## Environment variables

See `.env.example`:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CORS_ALLOWED_ORIGINS` — must include **every** origin that calls this API from the browser (defaults to `http://localhost:3000` only — add your deployed frontend origin(s) too, comma-separated)
- `DJANGO_AUTH_COOKIE_SAMESITE` / `DJANGO_AUTH_COOKIE_SECURE` — refresh-cookie attributes; defaults are dev-friendly (`Lax` / non-Secure when `DEBUG=True`), set explicitly in production (`None` / `True`) since the frontend and backend are different origins
- `DJANGO_EMAIL_HOST` / `DJANGO_EMAIL_PORT` / `DJANGO_EMAIL_HOST_USER` / `DJANGO_EMAIL_HOST_PASSWORD` / `DJANGO_EMAIL_USE_TLS` / `DJANGO_DEFAULT_FROM_EMAIL` — SMTP for real emails; unset in dev, so password-reset emails just print to the console
- `DEMO_REQUEST_NOTIFY_EMAIL` — where "Book a Demo" submissions get emailed; unset means no notification is sent (submissions are still saved and visible in `/admin/`)
- `DEMO_ACCOUNT_PASSWORD` — password for the seeded `demo` login (see above); defaults to `EvoHRDemo2026!` if unset
