from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .google_views import GoogleCallbackView, GoogleConnectUrlView, GoogleDisconnectView, GoogleStatusView
from .views import IntegrationCatalogView, IntegrationConnectionViewSet
from .webhook_views import CheckrWebhookView, DropboxSignWebhookView

router = DefaultRouter()
router.register('connections', IntegrationConnectionViewSet, basename='integration-connection')

urlpatterns = [
    path('catalog/', IntegrationCatalogView.as_view(), name='integration-catalog'),
    path('webhooks/checkr/<int:connection_id>/', CheckrWebhookView.as_view(), name='checkr-webhook'),
    path('webhooks/dropbox-sign/<int:connection_id>/', DropboxSignWebhookView.as_view(), name='dropbox-sign-webhook'),
    path('google/connect-url/', GoogleConnectUrlView.as_view(), name='google-connect-url'),
    path('google/callback/', GoogleCallbackView.as_view(), name='google-callback'),
    path('google/status/', GoogleStatusView.as_view(), name='google-status'),
    path('google/disconnect/', GoogleDisconnectView.as_view(), name='google-disconnect'),
    path('', include(router.urls)),
]
