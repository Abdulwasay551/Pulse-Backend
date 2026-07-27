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

## Role-based access control (HR vs. Employee)

`core.models.Organization` (a `name` + the HR user who created it) and `core.models.UserProfile` (one-to-one with `User`; `role` is `HR` or `Employee`; FK to `Organization`; FK to `people.Employee` when the profile is an Employee-role login) sit alongside the existing per-user ownership model rather than replacing it. Every owned row (`Candidate`, `Employee`, `PayrollRun`, etc.) is still scoped to a single "data owner" user id — `UserProfile.data_owner_id` is that id for both HR and Employee profiles in the same organization, so an invited employee's self-service views see the HR founder's data, not their own empty set.

- **Pre-existing accounts keep working with no migration**: a user with no `UserProfile` row at all (every account created before this feature shipped) is treated as full-access HR everywhere it matters — `core.permissions.is_hr_or_legacy()` and `UserSerializer`'s `role`/`organization`/`employee` fields (`SerializerMethodField`s) both default to HR/None/None when `request.user.profile` doesn't exist. HR-only actions (sending an invite, creating an employee login) lazily create the `Organization`+`UserProfile` on first use instead (`core/hr_views.py::get_or_create_hr_profile`).
- **Enforcement is one shared change**: `core.permissions.IsOwner.has_permission()` now also requires `is_hr_or_legacy(request)`, so every viewset that already used `IsOwner` (the large majority, across all four module apps) automatically became HR-only with zero per-viewset edits. The object-level `obj.owner_id == request.user.id` check is unchanged. A parallel `IsHR` permission (same list/create-level check, no object-level method) was added explicitly to the handful of viewsets that were never `IsOwner`-based because they're scoped through a parent object's `owner` instead of their own (`EmployeeDocumentViewSet`, `SurveyResponseViewSet`, `EnrollmentViewSet`, `OnboardingTaskViewSet`, `OffboardingTaskViewSet`) plus the three `*DashboardSummaryView`s and `EmployeeScoreView`.
- **Employee self-service is a separate, narrow surface**, not a relaxation of the module APIs: `core/my_views.py` exposes only `GET /api/my/dashboard/` (employee info, today's clock status, up to 10 goals, 6 most recent org activity-log entries), `POST /api/my/clock-in/`, `POST /api/my/clock-out/` — an Employee-role login has zero access to `/api/recruit/`, `/api/people/`, `/api/talent/`, `/api/payroll-benefits/` (blocked by the `IsOwner`/`IsHR` change above, a real 403, not just hidden in the UI).
- **Provisioning an employee login** — two flows, both HR-only (`IsHR`):
  - `POST /api/employee-accounts/` (`core/hr_views.py::EmployeeAccountCreateView`) — HR sets a username + password directly; the account can log in immediately.
  - `POST /api/employee-invites/` (`EmployeeInviteView`) — creates a `core.models.EmployeeInvite` (`token` UUID, `accepted_at` nullable) and emails a signup link (`FRONTEND_URL/signup?invite=<token>`); `GET /api/invites/<uuid:token>/` (`InviteDetailView`, `AllowAny`) lets the signup page show which org/employee the invite is for before the user sets a password. `RegisterSerializer` accepts an optional `invite_token` — when present and unaccepted, `register()` creates an Employee-role `UserProfile` linked to the invite's organization/employee and marks the invite accepted, instead of creating a brand-new `Organization`.

## Module apps

Every module API requires the access token and is scoped **per-user** — there's no team/org concept at the ownership layer, so a request only ever sees (and can only ever touch) rows where `owner == request.user` (enforced by the shared `core.permissions.IsOwner`; see the role-based access control section above for how HR vs. Employee logins layer on top of this). Accessing another user's object by ID returns a plain 404, not a 403 (so IDs don't even leak existence).

| App | Status | Models | API base path |
|---|---|---|---|
| `recruit` | **Real — fully built** | `Client`, `Requisition`, `Candidate`, `OfferLetter`, `BackgroundCheck`, `Onboarding`+`OnboardingTask`, `Offboarding`+`OffboardingTask` | `/api/recruit/` |
| `payroll_benefits` | **Real — fully built** | `PayrollRun`, `TaxProfile`, `ComplianceEvent`, `BankAccount`, `BenefitPlan`, `BenefitEnrollment`, `BenefitClaim` | `/api/payroll-benefits/` |
| `people` | **Real — fully built** | `Employee`, `EmployeeDocument`, `AttendanceRecord`, `Shift`, `LeaveRequest`, `Survey`+`SurveyResponse`, `Recognition`, `PromotionRequest` | `/api/people/` |
| `talent` | **Real — fully built** | `Goal`, `Appraisal`, `CompetencyRating`, `Course`+`Enrollment`, `CareerPath`, `SuccessionPlan` | `/api/talent/` |
| `it_assets` | **Real — fully built** | `Asset`, `SupportTicket`, `AssetIncident`, `BYODCompliance` | `/api/it-assets/` |

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

**Fully built — every sub-module in the spec is real.**

| Path | Model | Notable fields |
|---|---|---|
| `/api/payroll-benefits/payroll-runs/` | `PayrollRun` | `currency` (multi-currency support), `discrepancy_flagged`/`audit_notes` (Payroll Audit & Reconciliation Reports — annotated on the run itself, not a separate model, same reasoning as `Offboarding.rehire_notes`). Creating a run logs to `core.ActivityLog` (tone `amber` if status is `"Needs review"`, else `primary`) |
| `/api/payroll-benefits/tax-profiles/` | `TaxProfile` | `employee_detail`. Multi-Country Tax Compliance — one row per employee per country, with a `compliance_status` (`Compliant`/`Pending Review`/`Action Required`) |
| `/api/payroll-benefits/compliance-events/` | `ComplianceEvent` | The compliance-calendar half of "Multi-Currency Support & Compliance Calendar" — `calendar_status` (`Upcoming`/`Due soon`/`Overdue`/`Completed`) is computed live from `due_date`, not stored |
| `/api/payroll-benefits/bank-accounts/` | `BankAccount` | `employee_detail`. Direct Deposit / Banking Integration — only `account_number_last4` is ever persisted; the serializer accepts a write-only `account_number` and truncates it server-side, so a full account number never round-trips back to the client |
| `/api/payroll-benefits/benefit-plans/` | `BenefitPlan` | `enrolled_count`. The Benefits catalog (Health/Dental/Vision/Retirement/Life Insurance/Other) |
| `/api/payroll-benefits/benefit-enrollments/` | `BenefitEnrollment` | `employee_detail`, `plan_detail`. `enrolled_at`/`terminated_at` are set automatically the moment `status` transitions to `"Enrolled"`/`"Terminated"` |
| `/api/payroll-benefits/benefit-claims/` | `BenefitClaim` | `employee_detail`, `plan_name`. `resolved_at` is set automatically the moment `status` transitions to `"Approved"`/`"Rejected"`/`"Paid"`, which also logs to `core.ActivityLog` |

Plus `GET /api/payroll-benefits/dashboard-summary/` — `overview_stats`, `kpis` (discrepancies flagged, tax action required, compliance events overdue/due-soon), and `benefit_cost_by_type` + `total_monthly_benefit_cost` (both computed live from active enrollments × plan employer cost — this backs Benefit Cost Analysis, a computed view rather than a separate model).

`BankAccount`/`TaxProfile` are honest placeholders in the same spirit as Recruit's AI resume screening: real, working features today (bank details are stored and tracked, tax status is recorded and reviewable), deliberately built as a drop-in-replaceable seam for a future real banking-rail vendor (e.g. Plaid, Modern Treasury) or payroll-tax compliance service, since no such vendor account is provisioned for this project.

### EVO-People Management (`people`)

**Fully built — every sub-module in the spec is real.**

| Path | Model | Notable read-only computed fields |
|---|---|---|
| `/api/people/employees/` | `Employee` | `initials`, `manager_name`, `direct_reports_count`, nested `documents` |
| `/api/people/employee-documents/` | `EmployeeDocument` | Scoped via `employee__owner`, not its own `IsOwner` check |
| `/api/people/attendance-records/` | `AttendanceRecord` | `employee_detail`. Overtime Tracking is a filtered view over this (`overtime_hours > 0`), not a separate model |
| `/api/people/shifts/` | `Shift` | `employee_detail` |
| `/api/people/leave-requests/` | `LeaveRequest` | `employee_detail`. Approving/rejecting logs to `core.ActivityLog` |
| `/api/people/surveys/` | `Survey` | nested `responses`, `response_count`, `average_rating` — covers both Surveys and Pulse Checks via a `kind` field |
| `/api/people/survey-responses/` | `SurveyResponse` | `employee_detail`. Scoped via `survey__owner`, not its own `IsOwner` check |
| `/api/people/recognitions/` | `Recognition` | `employee_detail`. Creating one logs to `core.ActivityLog` |
| `/api/people/promotion-requests/` | `PromotionRequest` | `employee_detail`. Approving one writes `to_title`/`to_department` straight onto the `Employee` record — the workflow actually changes the record, not just logs it |

Plus:
- `GET /api/people/dashboard-summary/` — headcount/active/on-leave/department counts, a department breakdown, a status breakdown, and `kpis` (attrition rate, pending leave requests, pending promotions, open surveys) — all live, nothing cached.
- `GET /api/people/portal/<uuid:token>/` — **public, no auth** (`AllowAny`). Employee Self-Service: looked up by `Employee.portal_token` (unique UUID, auto-generated), returns `EmployeePortalSerializer`'s narrow field set (name, role, department, manager, hire date, status) — same reasoning as Recruit's Candidate Portal. Viewing payslips isn't included since `PayrollRun` isn't linked to individual employees yet.
- The same CSV export/import-preview/import-commit trio as `recruit/clients`, on `/api/people/employees/`.

`Employee.manager` is a self-referential FK — Organizational Chart (the frontend's `/dashboard/org-chart`) is a derived tree view over it, not a separate model. `Employee.source_candidate` optionally links back to a `recruit.Candidate` for people who came through EVO-Recruit, but isn't required — People also supports employees entered directly.

### EVO-Talent Management (`talent`)

**Fully built — every sub-module in the spec is real.**

| Path | Model | Notable read-only computed fields |
|---|---|---|
| `/api/talent/goals/` | `Goal` | `employee_detail` |
| `/api/talent/appraisals/` | `Appraisal` | `employee_detail` |
| `/api/talent/competency-ratings/` | `CompetencyRating` | `employee_detail` — backs both "Competency Mapping of Employees" (Goals & Appraisal) and "Skills & Competency Mapping" (Learning & Growth) in the frontend nav; one model, two entry points |
| `/api/talent/courses/` | `Course` | nested `enrollments` |
| `/api/talent/enrollments/` | `Enrollment` | `employee_detail`, `course_detail`. Scoped via `course__owner`, not its own `IsOwner` check |
| `/api/talent/career-paths/` | `CareerPath` | `employee_detail` |
| `/api/talent/succession-plans/` | `SuccessionPlan` | `employee_detail`. `potential_rating`/`performance_rating` (`Low`/`Medium`/`High`) place the row on a 9-box grid — the grid position is derived, not stored |

Plus:
- `GET /api/talent/employees/<id>/score/` (`IsHR`) — Value-Addition / Performance Scoring, "powered by EVO-AI" per the spec. `talent/scoring.py::compute_value_score` blends the employee's average goal `progress` with their average finalized-appraisal `overall_rating` (scaled to 0–100) into a single live score plus short notes — same "honest heuristic placeholder for a future real model" reasoning as Recruit's AI resume screening, since no ML/LLM vendor is provisioned.
- `GET /api/talent/dashboard-summary/` — `overview_stats`, `kpis` (course completion rate, ready-now successors, career paths mapped, competencies tracked), and `nine_box` (a `{potential}_{performance}: count` dict the frontend renders as an actual 3×3 grid table).

### EVO-IT & Asset Management (`it_assets`)

**Fully built — every sub-module in the spec is real.**

| Path | Model | Notable fields |
|---|---|---|
| `/api/it-assets/assets/` | `Asset` | `assigned_to_detail`, `warranty_status` (`Active`/`Expiring Soon`/`Expired`/`Unknown`, computed live from `warranty_expiry`), `open_ticket_count`. Device Provisioning is `assigned_to`/`assigned_at` being set or cleared on this same model — not a separate model — which also logs to `core.ActivityLog` |
| `/api/it-assets/support-tickets/` | `SupportTicket` | `employee_detail`, `asset_tag`. IT Support Requests Management — device queries and repair requests as a support-desk workflow. `resolved_at` is set automatically the moment `status` transitions to `"Resolved"`/`"Closed"` |
| `/api/it-assets/asset-incidents/` | `AssetIncident` | `employee_detail`, `asset_tag`/`asset_name`. Device Tracker — issue history, repairs, and damage records for a specific asset (distinct from `SupportTicket`, which is the request/workflow side) |
| `/api/it-assets/byod-checks/` | `BYODCompliance` | `employee_detail`, `asset_tag`. BYOD Security Policy — tracks encryption/antivirus/passcode checks and a `compliance_status` per personal device (an `Asset` with `is_byod=True`) |

Plus `GET /api/it-assets/dashboard-summary/` — `overview_stats` (total/assigned assets, open tickets, in-repair count) and `kpis` (warranties expiring soon/expired, unresolved incidents, non-compliant BYOD devices), all computed live. Warranty Tracking and Asset Inventory Tracking are both filtered/computed views over `Asset`, not separate models — same reasoning as People's Overtime Tracking and Recruit's Rehire & Alumni Pool.

### The demo account

`python manage.py seed_demo_account` creates (or resets) a `demo` user and fills it with a small realistic dataset across every real module — 8 clients, 6 requisitions, 10 candidates (two with resume text ready to screen), 5 payroll runs (one flagged with audit notes), a matching activity log, one sample offer letter, background check, in-progress onboarding (tasks across all 6 categories), in-progress offboarding (tasks across all 3 categories); for People, 6 employees across 2 departments with a 2-manager org chart, attendance records, a shift, two leave requests (one pending), an open pulse check with responses, a recognition, and a pending promotion request; for Talent, 2 goals, a finalized appraisal, 3 competency ratings, a course with 2 enrollments, a career path, and 2 succession plans; for Payroll & Benefits, 3 tax profiles (one needing action), 4 compliance events (one overdue-by-design, one completed), 2 bank accounts, 3 benefit plans with 4 enrollments across them, and 2 benefit claims; and for IT & Asset Management, 5 assets (4 assigned, one BYOD, one with a warranty expiring soon), 3 support tickets (one resolved), 2 incident records (one unresolved), and a compliant BYOD check — so anyone can log in as `demo` / `EvoHRDemo2026!` (or whatever `DEMO_ACCOUNT_PASSWORD` is set to) and see every built feature populated, not just the original candidates/clients/requisitions core. It's a **real account** with real rows, not a special-cased mode — every other signup just starts empty instead. The command (in `core/management/commands/`, since it seeds across `recruit`, `payroll_benefits`, `people`, `talent`, `it_assets`, and `core.ActivityLog`) is idempotent: re-running it wipes and re-creates only that one user's rows, so it's safe to use to reset the demo account after visitors have poked at it.

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
