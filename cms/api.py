from django.contrib.contenttypes.models import ContentType
from rest_framework.response import Response
from wagtail.api.v2.filters import FieldsFilter, OrderingFilter, SearchFilter
from wagtail.api.v2.router import WagtailAPIRouter
from wagtail.api.v2.views import BaseAPIViewSet, PagesAPIViewSet
from wagtail_headless_preview.models import PagePreview

from .models import Product, SiteSettings


class ProductAPIViewSet(BaseAPIViewSet):
    model = Product
    name = "products"
    filter_backends = [FieldsFilter, OrderingFilter, SearchFilter]
    listing_default_fields = BaseAPIViewSet.listing_default_fields + [
        field.name for field in Product.api_fields
    ]


class SiteSettingsAPIViewSet(BaseAPIViewSet):
    """Exposes the single SiteSettings row (shared nav/footer/CTA copy)."""

    model = SiteSettings
    name = "site-settings"
    filter_backends = [FieldsFilter]
    listing_default_fields = BaseAPIViewSet.listing_default_fields + [
        field.name for field in SiteSettings.api_fields
    ]


class PagePreviewAPIViewSet(PagesAPIViewSet):
    """Serves a draft page's data by preview token, in the same JSON shape
    as the live `pages` endpoint — used by the frontend's /preview route.
    See: https://github.com/torchbox/wagtail-headless-preview
    """

    known_query_parameters = PagesAPIViewSet.known_query_parameters.union(
        ["content_type", "token"]
    )

    def listing_view(self, request):
        # Delegate to detail_view so the frontend can hit /page_preview/
        # (no pk needed) — get_object() below resolves the page by token.
        self.action = "detail_view"
        return self.detail_view(request, 0)

    def detail_view(self, request, pk):
        page = self.get_object()
        serializer = self.get_serializer(page)
        return Response(serializer.data)

    def get_object(self):
        app_label, model = self.request.GET["content_type"].split(".")
        content_type = ContentType.objects.get(app_label=app_label, model=model)

        page_preview = PagePreview.objects.get(
            content_type=content_type, token=self.request.GET["token"]
        )
        page = page_preview.as_page()
        if not page.pk:
            # Fake primary key so the API URL routing doesn't complain.
            page.pk = 0

        return page


api_router = WagtailAPIRouter("wagtailapi")
api_router.register_endpoint("pages", PagesAPIViewSet)
api_router.register_endpoint("products", ProductAPIViewSet)
api_router.register_endpoint("site-settings", SiteSettingsAPIViewSet)
api_router.register_endpoint("page_preview", PagePreviewAPIViewSet)
