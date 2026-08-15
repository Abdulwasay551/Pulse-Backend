from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.documents import urls as wagtaildocs_urls

from core.views import health, landing
from cms.api import api_router

urlpatterns = [
    # Branded landing page — this backend is headless, so the root URL isn't a
    # real page (Next.js is the public site); point visitors at the two admins.
    path('', landing, name='landing'),

    # Unfold-themed Django admin (for non-CMS models: users, and each module app's data)
    path('admin/', admin.site.urls),
    # Wagtail CMS admin (separate surface, for editing marketing page content)
    path('cms/', include(wagtailadmin_urls)),
    path('documents/', include(wagtaildocs_urls)),

    path('api/health/', health, name='health'),
    # Headless content API consumed by the Next.js frontend
    path('api/cms/v2/', api_router.urls),
    # Auth (JWT via httpOnly cookie + in-memory access token) and other
    # non-CMS app API endpoints consumed by the Next.js frontend
    path('api/', include('core.urls')),
    # EVO-Recruit: fully built out, scoped per-user.
    path('api/recruit/', include('recruit.urls')),
    # EVO-Payroll & Benefits: fully built out, scoped per-user.
    path('api/payroll-benefits/', include('payroll_benefits.urls')),
    # EVO-People Management: fully built out, scoped per-user.
    path('api/people/', include('people.urls')),
    # EVO-Talent Management: fully built out, scoped per-user.
    path('api/talent/', include('talent.urls')),
    # EVO-IT & Asset Management: fully built out, scoped per-user.
    path('api/it-assets/', include('it_assets.urls')),
    # Bring-your-own-key AI provider integration (credentials, per-feature
    # model selection, and the status gate every AI-touched page checks).
    path('api/ai/', include('ai_core.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
