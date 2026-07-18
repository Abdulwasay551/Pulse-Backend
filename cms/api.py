from wagtail.api.v2.filters import FieldsFilter, OrderingFilter, SearchFilter
from wagtail.api.v2.router import WagtailAPIRouter
from wagtail.api.v2.views import BaseAPIViewSet, PagesAPIViewSet

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


api_router = WagtailAPIRouter("wagtailapi")
api_router.register_endpoint("pages", PagesAPIViewSet)
api_router.register_endpoint("products", ProductAPIViewSet)
api_router.register_endpoint("site-settings", SiteSettingsAPIViewSet)
