from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CandidateViewSet, ClientViewSet, DashboardSummaryView, PayrollRunViewSet, RequisitionViewSet

router = DefaultRouter()
router.register('clients', ClientViewSet, basename='client')
router.register('requisitions', RequisitionViewSet, basename='requisition')
router.register('candidates', CandidateViewSet, basename='candidate')
router.register('payroll-runs', PayrollRunViewSet, basename='payroll-run')

urlpatterns = [
    path('dashboard-summary/', DashboardSummaryView.as_view(), name='dashboard-summary'),
    path('', include(router.urls)),
]
