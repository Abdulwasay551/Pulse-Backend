from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    BackgroundCheckViewSet,
    CandidatePortalView,
    CandidateViewSet,
    ClientViewSet,
    DashboardSummaryView,
    OffboardingTaskViewSet,
    OffboardingViewSet,
    OfferLetterTemplateViewSet,
    OfferLetterViewSet,
    OnboardingTaskViewSet,
    OnboardingViewSet,
    RequisitionViewSet,
)

router = DefaultRouter()
router.register('clients', ClientViewSet, basename='client')
router.register('requisitions', RequisitionViewSet, basename='requisition')
router.register('candidates', CandidateViewSet, basename='candidate')
router.register('offer-letter-templates', OfferLetterTemplateViewSet, basename='offer-letter-template')
router.register('offer-letters', OfferLetterViewSet, basename='offer-letter')
router.register('background-checks', BackgroundCheckViewSet, basename='background-check')
router.register('onboardings', OnboardingViewSet, basename='onboarding')
router.register('onboarding-tasks', OnboardingTaskViewSet, basename='onboarding-task')
router.register('offboardings', OffboardingViewSet, basename='offboarding')
router.register('offboarding-tasks', OffboardingTaskViewSet, basename='offboarding-task')

urlpatterns = [
    path('dashboard-summary/', DashboardSummaryView.as_view(), name='recruit-dashboard-summary'),
    path('portal/<uuid:token>/', CandidatePortalView.as_view(), name='recruit-candidate-portal'),
    path('', include(router.urls)),
]
