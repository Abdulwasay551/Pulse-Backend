from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import PayrollRunViewSet

router = DefaultRouter()
router.register('payroll-runs', PayrollRunViewSet, basename='payroll-run')

urlpatterns = [
    path('', include(router.urls)),
]
