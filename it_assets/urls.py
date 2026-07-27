from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AssetIncidentViewSet,
    AssetViewSet,
    BYODComplianceViewSet,
    ItAssetsDashboardSummaryView,
    SupportTicketViewSet,
)

router = DefaultRouter()
router.register('assets', AssetViewSet, basename='asset')
router.register('support-tickets', SupportTicketViewSet, basename='support-ticket')
router.register('asset-incidents', AssetIncidentViewSet, basename='asset-incident')
router.register('byod-checks', BYODComplianceViewSet, basename='byod-check')

urlpatterns = [
    path('dashboard-summary/', ItAssetsDashboardSummaryView.as_view(), name='it-assets-dashboard-summary'),
    path('', include(router.urls)),
]
