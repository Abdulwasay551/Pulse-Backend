from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import (
    IsDepartmentHeadAppraisalAccess,
    IsDepartmentHeadReadOnly,
    IsDepartmentHeadWrite,
    IsHR,
    IsOwner,
    IsRecruiter,
    _role_is,
    owner_scope_id,
)
from people.models import Employee

from .models import (
    Appraisal,
    CareerPath,
    CompetencyRating,
    Course,
    Enrollment,
    Goal,
    RecruiterFeedback,
    SuccessionPlan,
)
from .scoring import compute_value_score
from .serializers import (
    AppraisalSerializer,
    CareerPathSerializer,
    CompetencyRatingSerializer,
    CourseSerializer,
    EnrollmentSerializer,
    GoalSerializer,
    RecruiterFeedbackSerializer,
    SuccessionPlanSerializer,
)


class OwnedTalentViewSet(viewsets.ModelViewSet):
    """Shared base — every Talent resource has its own `owner` field, so
    plain IsOwner + an owner-filtered queryset covers all of them."""

    permission_classes = [IsAuthenticated, IsOwner]

    def get_queryset(self):
        return self.queryset.filter(owner_id=owner_scope_id(self.request))

    def perform_create(self, serializer):
        serializer.save(owner_id=owner_scope_id(self.request))


class DepartmentScopedTalentViewSet(OwnedTalentViewSet):
    """Goal/CompetencyRating/CareerPath — working tools, so Department Head
    gets full create+update (no approval gate) scoped to their own
    department's employees, on top of HR/Admin's full access."""

    permission_classes = [IsAuthenticated, IsOwner | IsDepartmentHeadWrite]

    def get_queryset(self):
        qs = super().get_queryset()
        if _role_is(self.request, 'Department Head'):
            qs = qs.filter(employee__department=self.request.user.profile.department)
        return qs

    def perform_create(self, serializer):
        if _role_is(self.request, 'Department Head'):
            employee = serializer.validated_data['employee']
            if employee.department != self.request.user.profile.department:
                raise PermissionDenied("That employee isn't in your department.")
        serializer.save(owner_id=owner_scope_id(self.request))


class GoalViewSet(DepartmentScopedTalentViewSet):
    queryset = Goal.objects.select_related('employee').all()
    serializer_class = GoalSerializer


class AppraisalViewSet(OwnedTalentViewSet):
    """Department Head may create/update while drafting/submitting an
    appraisal for their own department's employees, but perform_update
    below blocks them from ever finalizing one — that stays HR/Admin-only,
    the "approval required" gate for Talent."""

    queryset = Appraisal.objects.select_related('employee').all()
    serializer_class = AppraisalSerializer
    permission_classes = [IsAuthenticated, IsOwner | IsDepartmentHeadAppraisalAccess]

    def get_queryset(self):
        qs = super().get_queryset()
        if _role_is(self.request, 'Department Head'):
            qs = qs.filter(employee__department=self.request.user.profile.department)
        return qs

    def perform_create(self, serializer):
        if _role_is(self.request, 'Department Head'):
            employee = serializer.validated_data['employee']
            if employee.department != self.request.user.profile.department:
                raise PermissionDenied("That employee isn't in your department.")
            if serializer.validated_data.get('status') == 'Finalized':
                raise PermissionDenied('Only HR or an Admin can finalize an appraisal.')
        serializer.save(owner_id=owner_scope_id(self.request))

    def perform_update(self, serializer):
        new_status = serializer.validated_data.get('status', serializer.instance.status)
        if new_status == 'Finalized' and _role_is(self.request, 'Department Head'):
            raise PermissionDenied('Only HR or an Admin can finalize an appraisal.')
        serializer.save()


class CompetencyRatingViewSet(DepartmentScopedTalentViewSet):
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
        return self.queryset.filter(course__owner_id=owner_scope_id(self.request))


class CareerPathViewSet(DepartmentScopedTalentViewSet):
    queryset = CareerPath.objects.select_related('employee').all()
    serializer_class = CareerPathSerializer


class SuccessionPlanViewSet(viewsets.ModelViewSet):
    """View-only for Department Head — succession planning isn't in their
    write list."""

    queryset = SuccessionPlan.objects.select_related('employee').all()
    serializer_class = SuccessionPlanSerializer
    permission_classes = [IsAuthenticated, IsOwner | IsDepartmentHeadReadOnly]

    def get_queryset(self):
        qs = self.queryset.filter(owner_id=owner_scope_id(self.request))
        if _role_is(self.request, 'Department Head'):
            qs = qs.filter(employee__department=self.request.user.profile.department)
        return qs

    def perform_create(self, serializer):
        serializer.save(owner_id=owner_scope_id(self.request))


class RecruiterFeedbackViewSet(viewsets.ModelViewSet):
    """Recruiter creates feedback notes on a placed/hired employee; HR
    views them (read-only for HR even though IsHR is OR'd in — enforced by
    the explicit role check in perform_create, not by http_method_names,
    since HR still needs list/retrieve)."""

    http_method_names = ['get', 'post', 'head', 'options']
    queryset = RecruiterFeedback.objects.select_related('employee').all()
    serializer_class = RecruiterFeedbackSerializer
    permission_classes = [IsAuthenticated, IsRecruiter | IsHR]

    def get_queryset(self):
        return self.queryset.filter(owner_id=owner_scope_id(self.request))

    def perform_create(self, serializer):
        if not _role_is(self.request, 'Recruiter'):
            raise PermissionDenied('Only Recruiter accounts can log feedback.')
        serializer.save(owner_id=owner_scope_id(self.request))


class EmployeeScoreView(APIView):
    """Value-Addition / Performance Scoring, "powered by EVO-AI" per the
    spec — see talent/scoring.py. Computed live from the employee's own
    goals + appraisals, nothing stored."""

    permission_classes = [IsAuthenticated, IsHR]

    def get(self, request, employee_id):
        employee = get_object_or_404(Employee, id=employee_id, owner_id=owner_scope_id(request))
        score, notes = compute_value_score(employee)
        return Response({'employee': employee.id, 'score': score, 'notes': notes})


class TalentDashboardSummaryView(APIView):
    """EVO-Talent's overview numbers, computed live from the user's own
    rows — nothing here is stored/cached."""

    permission_classes = [IsAuthenticated, IsHR]

    def get(self, request):
        uid = owner_scope_id(request)
        goals = Goal.objects.filter(owner_id=uid)
        appraisals = Appraisal.objects.filter(owner_id=uid)
        courses = Course.objects.filter(owner_id=uid)
        enrollments = Enrollment.objects.filter(course__owner_id=uid)
        succession_plans = SuccessionPlan.objects.filter(owner_id=uid)

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
                    {'label': 'Career paths mapped', 'value': str(CareerPath.objects.filter(owner_id=uid).count()), 'href': '/dashboard/career-paths'},
                    {'label': 'Competencies tracked', 'value': str(CompetencyRating.objects.filter(owner_id=uid).count()), 'href': '/dashboard/competency-mapping'},
                ],
                'nine_box': nine_box,
            }
        )
