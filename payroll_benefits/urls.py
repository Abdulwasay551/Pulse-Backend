from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    BankAccountViewSet,
    BenefitClaimViewSet,
    BenefitEnrollmentViewSet,
    BenefitPlanViewSet,
    ComplianceEventViewSet,
    ExchangeRateViewSet,
    ExternalWorkforceView,
    PayrollBenefitsDashboardSummaryView,
    PayrollRunViewSet,
    TaxProfileViewSet,
)

router = DefaultRouter()
router.register('payroll-runs', PayrollRunViewSet, basename='payroll-run')
router.register('exchange-rates', ExchangeRateViewSet, basename='exchange-rate')
router.register('tax-profiles', TaxProfileViewSet, basename='tax-profile')
router.register('compliance-events', ComplianceEventViewSet, basename='compliance-event')
router.register('bank-accounts', BankAccountViewSet, basename='bank-account')
router.register('benefit-plans', BenefitPlanViewSet, basename='benefit-plan')
router.register('benefit-enrollments', BenefitEnrollmentViewSet, basename='benefit-enrollment')
router.register('benefit-claims', BenefitClaimViewSet, basename='benefit-claim')

urlpatterns = [
    path('dashboard-summary/', PayrollBenefitsDashboardSummaryView.as_view(), name='payroll-benefits-dashboard-summary'),
    path('external-workforce/<str:provider>/', ExternalWorkforceView.as_view(), name='payroll-external-workforce'),
    path('', include(router.urls)),
]
