from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import IntegrationCatalogView, IntegrationConnectionViewSet

router = DefaultRouter()
router.register('connections', IntegrationConnectionViewSet, basename='integration-connection')

urlpatterns = [
    path('catalog/', IntegrationCatalogView.as_view(), name='integration-catalog'),
    path('', include(router.urls)),
]
