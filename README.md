# EvoHR Backend

Django backend for **EvoHR** — a recruitment CRM & ATS for staffing agencies, in the vein of RecruitCRM. This service provides:

- A headless **Wagtail CMS** for all public marketing page content (home, pricing, solutions, use cases, who we serve, resources), consumed by the separate [EvoHR frontend](https://github.com/Abdulwasay551/EvoHR-Frontend) over a REST API.
- A **Django admin** themed with [django-unfold](https://github.com/unfoldadmin/django-unfold), kept separate from the CMS admin and reserved for non-CMS data (users today; CRM entities — candidates, clients, placements — as the product grows).

## Stack

- Django 5.2 + Django REST Framework
- Wagtail 7 (CMS + headless API v2)
- django-unfold (Django admin theme)
- SQLite (dev)

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
| `/admin/` | Django admin (Unfold theme) — users and future CRM data |
| `/api/cms/v2/` | Headless REST API consumed by the Next.js frontend (`pages`, `products`, `site-settings`) |
| `/api/health/` | Health check |

## Environment variables

See `.env.example`:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CORS_ALLOWED_ORIGINS` — must include the frontend's origin (defaults to `http://localhost:3000`)
