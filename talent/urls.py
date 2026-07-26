from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AppraisalViewSet,
    CareerPathViewSet,
    CompetencyRatingViewSet,
    CourseViewSet,
    EmployeeScoreView,
    EnrollmentViewSet,
    GoalViewSet,
    SuccessionPlanViewSet,
    TalentDashboardSummaryView,
)

router = DefaultRouter()
router.register('goals', GoalViewSet, basename='goal')
router.register('appraisals', AppraisalViewSet, basename='appraisal')
router.register('competency-ratings', CompetencyRatingViewSet, basename='competency-rating')
router.register('courses', CourseViewSet, basename='course')
router.register('enrollments', EnrollmentViewSet, basename='enrollment')
router.register('career-paths', CareerPathViewSet, basename='career-path')
router.register('succession-plans', SuccessionPlanViewSet, basename='succession-plan')

urlpatterns = [
    path('dashboard-summary/', TalentDashboardSummaryView.as_view(), name='talent-dashboard-summary'),
    path('employees/<int:employee_id>/score/', EmployeeScoreView.as_view(), name='talent-employee-score'),
    path('', include(router.urls)),
]
