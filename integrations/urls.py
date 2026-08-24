from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import IntegrationCatalogView, IntegrationConnectionViewSet
from .webhook_views import CheckrWebhookView, DropboxSignWebhookView

router = DefaultRouter()
router.register('connections', IntegrationConnectionViewSet, basename='integration-connection')

urlpatterns = [
    path('catalog/', IntegrationCatalogView.as_view(), name='integration-catalog'),
    path('webhooks/checkr/<int:connection_id>/', CheckrWebhookView.as_view(), name='checkr-webhook'),
    path('webhooks/dropbox-sign/<int:connection_id>/', DropboxSignWebhookView.as_view(), name='dropbox-sign-webhook'),
    path('', include(router.urls)),
]
