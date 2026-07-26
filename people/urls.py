from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AttendanceRecordViewSet,
    EmployeeDocumentViewSet,
    EmployeePortalView,
    EmployeeViewSet,
    LeaveRequestViewSet,
    PeopleDashboardSummaryView,
    PromotionRequestViewSet,
    RecognitionViewSet,
    ShiftViewSet,
    SurveyResponseViewSet,
    SurveyViewSet,
)

router = DefaultRouter()
router.register('employees', EmployeeViewSet, basename='employee')
router.register('employee-documents', EmployeeDocumentViewSet, basename='employee-document')
router.register('attendance-records', AttendanceRecordViewSet, basename='attendance-record')
router.register('shifts', ShiftViewSet, basename='shift')
router.register('leave-requests', LeaveRequestViewSet, basename='leave-request')
router.register('surveys', SurveyViewSet, basename='survey')
router.register('survey-responses', SurveyResponseViewSet, basename='survey-response')
router.register('recognitions', RecognitionViewSet, basename='recognition')
router.register('promotion-requests', PromotionRequestViewSet, basename='promotion-request')

urlpatterns = [
    path('dashboard-summary/', PeopleDashboardSummaryView.as_view(), name='people-dashboard-summary'),
    path('portal/<uuid:token>/', EmployeePortalView.as_view(), name='people-employee-portal'),
    path('', include(router.urls)),
]
