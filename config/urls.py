from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from wagtail.admin import urls as wagtailadmin_urls
from wagtail import urls as wagtail_urls
from wagtail.documents import urls as wagtaildocs_urls

from core.views import health
from cms.api import api_router

urlpatterns = [
    # Unfold-themed Django admin (for non-CMS models: users, and future CRM data)
    path('admin/', admin.site.urls),
    # Wagtail CMS admin (separate surface, for editing marketing page content)
    path('cms/', include(wagtailadmin_urls)),
    path('documents/', include(wagtaildocs_urls)),

    path('api/health/', health, name='health'),
    # Headless content API consumed by the Next.js frontend
    path('api/cms/v2/', api_router.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

urlpatterns += [
    # Wagtail page serving — only used for the admin's preview panel, not by the
    # (separate) Next.js frontend, which reads content through api/cms/v2/ instead.
    path('', include(wagtail_urls)),
]
