from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsHR, IsOwner
from people.models import Employee

from .models import Appraisal, CareerPath, CompetencyRating, Course, Enrollment, Goal, SuccessionPlan
from .scoring import compute_value_score
from .serializers import (
    AppraisalSerializer,
    CareerPathSerializer,
    CompetencyRatingSerializer,
    CourseSerializer,
    EnrollmentSerializer,
    GoalSerializer,
    SuccessionPlanSerializer,
)


class OwnedTalentViewSet(viewsets.ModelViewSet):
    """Shared base — every Talent resource has its own `owner` field, so
    plain IsOwner + an owner-filtered queryset covers all of them."""

    permission_classes = [IsAuthenticated, IsOwner]

    def get_queryset(self):
        return self.queryset.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class GoalViewSet(OwnedTalentViewSet):
    queryset = Goal.objects.select_related('employee').all()
    serializer_class = GoalSerializer


class AppraisalViewSet(OwnedTalentViewSet):
    queryset = Appraisal.objects.select_related('employee').all()
    serializer_class = AppraisalSerializer


class CompetencyRatingViewSet(OwnedTalentViewSet):
    queryset = CompetencyRating.objects.select_related('employee').all()
    serializer_class = CompetencyRatingSerializer


class CourseViewSet(OwnedTalentViewSet):
    queryset = Course.objects.prefetch_related('enrollments').all()
    serializer_class = CourseSerializer


class EnrollmentViewSet(viewsets.ModelViewSet):
    """No IsOwner — Enrollment has no `owner` field of its own, scoped via
    its parent Course's owner, same reasoning as EmployeeDocument."""

    queryset = Enrollment.objects.select_related('employee', 'course').all()
    serializer_class = EnrollmentSerializer
    permission_classes = [IsAuthenticated, IsHR]

    def get_queryset(self):
        return self.queryset.filter(course__owner=self.request.user)


class CareerPathViewSet(OwnedTalentViewSet):
    queryset = CareerPath.objects.select_related('employee').all()
    serializer_class = CareerPathSerializer


class SuccessionPlanViewSet(OwnedTalentViewSet):
    queryset = SuccessionPlan.objects.select_related('employee').all()
    serializer_class = SuccessionPlanSerializer


class EmployeeScoreView(APIView):
    """Value-Addition / Performance Scoring, "powered by EVO-AI" per the
    spec — see talent/scoring.py. Computed live from the employee's own
    goals + appraisals, nothing stored."""

    permission_classes = [IsAuthenticated, IsHR]

    def get(self, request, employee_id):
        employee = get_object_or_404(Employee, id=employee_id, owner=request.user)
        score, notes = compute_value_score(employee)
        return Response({'employee': employee.id, 'score': score, 'notes': notes})


class TalentDashboardSummaryView(APIView):
    """EVO-Talent's overview numbers, computed live from the user's own
    rows — nothing here is stored/cached."""

    permission_classes = [IsAuthenticated, IsHR]

    def get(self, request):
        user = request.user
        goals = Goal.objects.filter(owner=user)
        appraisals = Appraisal.objects.filter(owner=user)
        courses = Course.objects.filter(owner=user)
        enrollments = Enrollment.objects.filter(course__owner=user)
        succession_plans = SuccessionPlan.objects.filter(owner=user)

        goals_in_progress = goals.filter(status='In Progress').count()
        goals_completed = goals.filter(status='Completed').count()
        completed_enrollments = enrollments.filter(status='Completed').count()
        completion_rate = round(completed_enrollments / enrollments.count() * 100) if enrollments.count() else 0
        ready_now = succession_plans.filter(ready_now=True).count()

        # 9-box grid — potential x performance counts, for the frontend to
        # render as an actual 3x3 grid rather than a flat list.
        nine_box = {}
        for potential, _ in SuccessionPlan.RATING_CHOICES:
            for performance, _ in SuccessionPlan.RATING_CHOICES:
                count = succession_plans.filter(potential_rating=potential, performance_rating=performance).count()
                nine_box[f'{potential}_{performance}'] = count

        return Response(
            {
                'overview_stats': [
                    {'label': 'Goals in progress', 'value': str(goals_in_progress), 'change': '', 'href': '/dashboard/goals'},
                    {'label': 'Goals completed', 'value': str(goals_completed), 'change': '', 'href': '/dashboard/goals'},
                    {'label': 'Appraisals on file', 'value': str(appraisals.count()), 'change': '', 'href': '/dashboard/appraisals'},
                    {'label': 'Active courses', 'value': str(courses.filter(is_active=True).count()), 'change': '', 'href': '/dashboard/learning'},
                ],
                'kpis': [
                    {'label': 'Course completion rate', 'value': f'{completion_rate}%', 'href': '/dashboard/learning'},
                    {'label': 'Ready-now successors', 'value': str(ready_now), 'href': '/dashboard/succession-planning'},
                    {'label': 'Career paths mapped', 'value': str(CareerPath.objects.filter(owner=user).count()), 'href': '/dashboard/career-paths'},
                    {'label': 'Competencies tracked', 'value': str(CompetencyRating.objects.filter(owner=user).count()), 'href': '/dashboard/competency-mapping'},
                ],
                'nine_box': nine_box,
            }
        )
