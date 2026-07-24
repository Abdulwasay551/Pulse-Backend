# EvoHR Backend

Django backend for **EvoHR** — a recruitment CRM & ATS for staffing agencies, in the vein of RecruitCRM. This service provides:

- A headless **Wagtail CMS** for all public marketing page content (home, pricing, solutions, use cases, who we serve, resources), consumed by the separate [EvoHR frontend](https://github.com/Abdulwasay551/EvoHR-Frontend) over a REST API.
- A **Django admin** themed with [django-unfold](https://github.com/unfoldadmin/django-unfold), kept separate from the CMS admin and reserved for non-CMS data (users, demo requests today; more CRM entities — candidates, clients, placements — as the product grows).
- A **JWT-based auth API** (`core` app) — register/login/logout, forgot/reset/change password, profile — used by the frontend's real login/signup/dashboard flow.
- The **"Book a Demo"** lead-capture endpoint behind the marketing site's demo-request form.

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
python manage.py seed_cms  # seeds the page tree, products, and site settings (idempotent, first run only)
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

## Environment variables

See `.env.example`:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CORS_ALLOWED_ORIGINS` — must include **every** origin that calls this API from the browser (defaults to `http://localhost:3000` only — add your deployed frontend origin(s) too, comma-separated)
- `DJANGO_AUTH_COOKIE_SAMESITE` / `DJANGO_AUTH_COOKIE_SECURE` — refresh-cookie attributes; defaults are dev-friendly (`Lax` / non-Secure when `DEBUG=True`), set explicitly in production (`None` / `True`) since the frontend and backend are different origins
- `DJANGO_EMAIL_HOST` / `DJANGO_EMAIL_PORT` / `DJANGO_EMAIL_HOST_USER` / `DJANGO_EMAIL_HOST_PASSWORD` / `DJANGO_EMAIL_USE_TLS` / `DJANGO_DEFAULT_FROM_EMAIL` — SMTP for real emails; unset in dev, so password-reset emails just print to the console
- `DEMO_REQUEST_NOTIFY_EMAIL` — where "Book a Demo" submissions get emailed; unset means no notification is sent (submissions are still saved and visible in `/admin/`)
