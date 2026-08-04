from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from it_assets.models import SupportTicket
from it_assets.serializers import SupportTicketSerializer
from payroll_benefits.models import BenefitClaim
from payroll_benefits.serializers import BenefitClaimSerializer
from people.models import AttendanceRecord
from people.serializers import EmployeeLiteSerializer
from recruit.serializers import OnboardingTaskSerializer
from talent.models import Appraisal, CompetencyRating, Goal
from talent.serializers import AppraisalSerializer, CompetencyRatingSerializer, GoalSerializer

from .models import ActivityLog


def _relative_time(dt):
    delta = timezone.now() - dt
    seconds = delta.total_seconds()
    if seconds < 60:
        return 'just now'
    if seconds < 3600:
        return f'{int(seconds // 60)}m ago'
    if seconds < 86400:
        return f'{int(seconds // 3600)}h ago'
    return f'{int(seconds // 86400)}d ago'


def _employee_profile_or_error(request):
    """Every view in this module is Employee-role self-service — resolves
    the requesting user's linked people.Employee record, or None (plus an
    error Response to short-circuit with) if this login isn't set up as an
    Employee account."""
    profile = getattr(request.user, 'profile', None)
    if not profile or profile.role != 'Employee' or not profile.employee_id:
        return None, Response({'detail': 'This account is not set up as an employee.'}, status=400)
    return profile, None


class MyDashboardView(APIView):
    """What an Employee-role login sees on their own dashboard: their
    profile, today's clock-in status, their goals, and the organization's
    recent activity feed — all read live, nothing cached."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile, error = _employee_profile_or_error(request)
        if error:
            return error

        employee = profile.employee
        today = timezone.now().date()
        attendance_today = AttendanceRecord.objects.filter(employee=employee, date=today).first()
        goals = Goal.objects.filter(employee=employee).order_by('-created_at')[:10]
        activity = ActivityLog.objects.filter(owner_id=profile.data_owner_id)[:6]

        return Response(
            {
                'employee': EmployeeLiteSerializer(employee).data,
                'attendance_today': (
                    {
                        'clock_in': attendance_today.clock_in,
                        'clock_out': attendance_today.clock_out,
                    }
                    if attendance_today
                    else None
                ),
                'goals': GoalSerializer(goals, many=True).data,
                'recent_activity': [
                    {'id': str(item.id), 'message': item.message, 'time': _relative_time(item.created_at), 'tone': item.tone}
                    for item in activity
                ],
            }
        )


class ClockInView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        profile, error = _employee_profile_or_error(request)
        if error:
            return error

        today = timezone.now().date()
        record, _ = AttendanceRecord.objects.get_or_create(
            employee=profile.employee, date=today, defaults={'owner_id': profile.data_owner_id}
        )
        if not record.clock_in:
            record.clock_in = timezone.now().time()
            record.save(update_fields=['clock_in'])
        return Response({'clock_in': record.clock_in, 'clock_out': record.clock_out})


class ClockOutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        profile, error = _employee_profile_or_error(request)
        if error:
            return error

        today = timezone.now().date()
        record = AttendanceRecord.objects.filter(employee=profile.employee, date=today).first()
        if record is None or not record.clock_in:
            return Response({'detail': 'Clock in before clocking out.'}, status=400)
        record.clock_out = timezone.now().time()
        record.save(update_fields=['clock_out'])
        return Response({'clock_in': record.clock_in, 'clock_out': record.clock_out})


class MyOnboardingChecklistView(APIView):
    """An Employee's own onboarding checklist — Onboarding/OnboardingTask
    actually live in the recruit app keyed off Candidate, not Employee, so
    this resolves the link back through Employee.source_candidate. Employees
    added directly (never a Candidate) simply have no checklist to show."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile, error = _employee_profile_or_error(request)
        if error:
            return error

        candidate = profile.employee.source_candidate
        onboarding = getattr(candidate, 'onboarding', None) if candidate else None
        if onboarding is None:
            return Response({'onboarding': None, 'tasks': []})
        return Response(
            {
                'onboarding': {'status': onboarding.status, 'start_date': onboarding.start_date},
                'tasks': OnboardingTaskSerializer(onboarding.tasks.all(), many=True).data,
            }
        )


class MyTalentView(APIView):
    """An Employee's own Talent Management records — read-only."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile, error = _employee_profile_or_error(request)
        if error:
            return error

        employee = profile.employee
        return Response(
            {
                'goals': GoalSerializer(Goal.objects.filter(employee=employee), many=True).data,
                'appraisals': AppraisalSerializer(Appraisal.objects.filter(employee=employee), many=True).data,
                'competency_ratings': CompetencyRatingSerializer(
                    CompetencyRating.objects.filter(employee=employee), many=True
                ).data,
            }
        )


class MyBenefitClaimsView(APIView):
    """An Employee submits and views only their own benefit claims."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile, error = _employee_profile_or_error(request)
        if error:
            return error
        claims = BenefitClaim.objects.filter(employee=profile.employee)
        return Response(BenefitClaimSerializer(claims, many=True).data)

    def post(self, request):
        profile, error = _employee_profile_or_error(request)
        if error:
            return error
        # An employee submits a claim, they don't get to decide its
        # status — strip it so the model default ('Submitted') always wins,
        # no matter what the request body contains.
        data = {k: v for k, v in request.data.items() if k != 'status'}
        serializer = BenefitClaimSerializer(
            data={**data, 'employee': profile.employee_id}, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(owner_id=profile.data_owner_id)
        return Response(serializer.data, status=201)


class MySupportTicketsView(APIView):
    """An Employee submits and views only their own IT support tickets."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile, error = _employee_profile_or_error(request)
        if error:
            return error
        tickets = SupportTicket.objects.filter(employee=profile.employee)
        return Response(SupportTicketSerializer(tickets, many=True).data)

    def post(self, request):
        profile, error = _employee_profile_or_error(request)
        if error:
            return error
        # Same reasoning as MyBenefitClaimsView — an employee doesn't get
        # to set a ticket's status; it always starts at the model default
        # ('Open').
        data = {k: v for k, v in request.data.items() if k != 'status'}
        serializer = SupportTicketSerializer(
            data={**data, 'employee': profile.employee_id}, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(owner_id=profile.data_owner_id)
        return Response(serializer.data, status=201)
