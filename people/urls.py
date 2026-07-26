from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import EmployeeDocumentViewSet, EmployeeViewSet, PeopleDashboardSummaryView

router = DefaultRouter()
router.register('employees', EmployeeViewSet, basename='employee')
router.register('employee-documents', EmployeeDocumentViewSet, basename='employee-document')

urlpatterns = [
    path('dashboard-summary/', PeopleDashboardSummaryView.as_view(), name='people-dashboard-summary'),
    path('', include(router.urls)),
]
