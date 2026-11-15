from datetime import timedelta

from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from it_assets.models import BYODCompliance, SupportTicket
from it_assets.serializers import SupportTicketSerializer
from payroll_benefits.models import BenefitClaim, PayrollRun
from payroll_benefits.serializers import BenefitClaimSerializer
from people.models import AttendanceRecord, LeaveRequest, Task
from people.serializers import EmployeeLiteSerializer, TaskSerializer
from recruit.serializers import OnboardingTaskSerializer
from talent.models import Appraisal, CompetencyRating, Goal
from talent.serializers import AppraisalSerializer, CompetencyRatingSerializer, GoalSerializer

from .health import compute_health
from .models import ActivityLog
from .weather import get_weather_for_location


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
    """Every view in this module is self-service for any employee-linked
    login — resolves the requesting user's linked people.Employee record,
    or None (plus an error Response to short-circuit with) if this login
    isn't set up as one. Employee and Contractor both qualify (Contractor
    is "a restricted Employee variant" per the Control Hierarchy Matrix —
    same self-service surface, narrower access elsewhere, enforced by
    core.access_matrix on the module viewsets, not here)."""
    profile = getattr(request.user, 'profile', None)
    if not profile or profile.role not in ('Employee', 'Contractor') or not profile.employee_id:
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
        # .date() straight off timezone.now() would read off UTC's
        # calendar day regardless of TIME_ZONE (settings.TIME_ZONE only
        # governs conversions through timezone.localtime(), never
        # timezone.now() itself) — localtime() first so "today" lines up
        # with the org's actual local day (Asia/Karachi).
        today = timezone.localtime(timezone.now()).date()
        month_start = today.replace(day=1)
        soon = today + timedelta(days=7)
        attendance_today = AttendanceRecord.objects.filter(employee=employee, date=today).first()
        # Unsliced — goals_due_soon/active_goals below need to keep
        # filtering/excluding on it; `goals` (sliced, for the serialized
        # display list only) is derived from this further down, since a
        # QuerySet can't be filtered again once a slice has been taken.
        goals_qs = Goal.objects.filter(employee=employee).order_by('-created_at')
        goals = goals_qs[:10]
        activity = ActivityLog.objects.filter(owner_id=profile.data_owner_id)[:6]

        # "MY PENDING TASKS" — every flagged item that's actually this
        # employee's own to act on, across the four modules that can flag
        # something at them individually (not org-wide counts).
        open_tickets = SupportTicket.objects.filter(employee=employee).exclude(status__in=['Resolved', 'Closed'])
        claims_in_review = BenefitClaim.objects.filter(employee=employee, status__in=['Submitted', 'Under Review'])
        goals_due_soon = goals_qs.filter(status__in=['Not Started', 'In Progress'], target_date__isnull=False, target_date__lte=soon)
        byod_flags = BYODCompliance.objects.filter(employee=employee, compliance_status='Non-Compliant')
        open_assigned_tasks = Task.objects.filter(employee=employee).exclude(status='Completed')

        pending_tasks = (
            [
                {
                    'id': f'ticket-{t.id}', 'label': f'IT ticket #{t.id} — {t.subject}',
                    'status': t.status, 'tone': 'amber', 'href': '/dashboard/settings',
                }
                for t in open_tickets
            ]
            + [
                {
                    'id': f'claim-{c.id}', 'label': f'{c.claim_type} claim — under review',
                    'status': c.status, 'tone': 'amber', 'href': '/dashboard/settings',
                }
                for c in claims_in_review
            ]
            + [
                {
                    'id': f'goal-{g.id}', 'label': f'Goal check-in due: {g.title}',
                    'status': 'Due' if g.target_date and g.target_date < today else 'Due soon', 'tone': 'maroon',
                    'href': '/dashboard/settings',
                }
                for g in goals_due_soon
            ]
            + [
                {
                    'id': f'byod-{b.id}', 'label': 'BYOD compliance acknowledgement needed',
                    'status': 'Action', 'tone': 'maroon', 'href': '/dashboard/settings',
                }
                for b in byod_flags
            ]
            + [
                {
                    'id': f'task-{t.id}', 'label': f'Task: {t.title}',
                    'status': t.status, 'tone': 'amber', 'href': '/dashboard',
                }
                for t in open_assigned_tasks
            ]
        )

        work_health = compute_health(
            {
                'You': {
                    'awaiting_input_tickets': open_tickets.count(),
                    'claims_under_review': claims_in_review.count(),
                    'goal_check_ins_due': goals_due_soon.count(),
                    'compliance_acks_needed': byod_flags.count(),
                }
            }
        )

        # "THIS MONTH" — only figures the data actually supports; no
        # fabricated leave-balance/payday-date since neither an accrual
        # system nor a pay-date field exists anywhere in the schema.
        hours_logged = 0.0
        for record in AttendanceRecord.objects.filter(employee=employee, date__gte=month_start):
            if record.clock_in and record.clock_out:
                start = timezone.datetime.combine(record.date, record.clock_in)
                end = timezone.datetime.combine(record.date, record.clock_out)
                hours_logged += max(0, (end - start).total_seconds() / 3600)
        leave_requests_this_month = LeaveRequest.objects.filter(
            employee=employee, status='Approved', start_date__gte=month_start
        ).count()
        latest_payroll_run = PayrollRun.objects.filter(owner_id=profile.data_owner_id).first()
        active_goals = goals_qs.exclude(status='Completed')
        goal_progress = round(sum(g.progress for g in active_goals) / len(active_goals)) if active_goals else 0

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
                'work_health': work_health,
                'pending_tasks': pending_tasks,
                'this_month': {
                    'hours_logged': round(hours_logged, 1),
                    'approved_leave_requests': leave_requests_this_month,
                    'current_pay_period': latest_payroll_run.period if latest_payroll_run else None,
                    'goal_progress': goal_progress,
                },
                'weather': get_weather_for_location(employee.location),
            }
        )


class ClockInView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        profile, error = _employee_profile_or_error(request)
        if error:
            return error

        now = timezone.localtime(timezone.now())
        today = now.date()
        record, _ = AttendanceRecord.objects.get_or_create(
            employee=profile.employee, date=today, defaults={'owner_id': profile.data_owner_id}
        )
        if not record.clock_in:
            # Hour/minute only — clock times are an HH:MM read, not a
            # stopwatch, and dropping seconds/microseconds here keeps every
            # consumer (admin table, employee widget, exports) clean without
            # each one having to re-trim what it's handed.
            record.clock_in = now.time().replace(second=0, microsecond=0)
            record.save(update_fields=['clock_in'])
        return Response({'clock_in': record.clock_in, 'clock_out': record.clock_out})


class ClockOutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        profile, error = _employee_profile_or_error(request)
        if error:
            return error

        now = timezone.localtime(timezone.now())
        today = now.date()
        record = AttendanceRecord.objects.filter(employee=profile.employee, date=today).first()
        if record is None or not record.clock_in:
            return Response({'detail': 'Clock in before clocking out.'}, status=400)
        record.clock_out = now.time().replace(second=0, microsecond=0)
        if 'notes' in request.data:
            # Clocking out prompts "what did you get done today?" on the
            # frontend — appended (not overwritten) since a clock-in note
            # may already be sitting in this field.
            addition = str(request.data.get('notes') or '').strip()
            if addition:
                record.notes = f'{record.notes}\n{addition}'.strip() if record.notes else addition
        record.save(update_fields=['clock_out', 'notes'])
        return Response({'clock_in': record.clock_in, 'clock_out': record.clock_out, 'notes': record.notes})


class MyTasksView(APIView):
    """An Employee's own tasks, assigned by their manager/HR through
    people.TaskViewSet — read-only here (creating/editing a task stays
    manager/HR-only there); marking one done is the separate, narrower
    MyTaskCompleteView below, the same self-service split every other row
    in this module uses. Surfaced on the dashboard and in the clock-out
    prompt ("what did you finish today")."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile, error = _employee_profile_or_error(request)
        if error:
            return error
        tasks = Task.objects.filter(employee=profile.employee).select_related('assigned_by').order_by(
            'status', '-created_at'
        )
        return Response(TaskSerializer(tasks, many=True).data)


class MyTaskCompleteView(APIView):
    """Marks one of the caller's own tasks Completed (or back to In
    Progress/Pending), optionally with completion notes — what the
    clock-out prompt posts to per task the employee checks off."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        profile, error = _employee_profile_or_error(request)
        if error:
            return error
        task = Task.objects.filter(pk=pk, employee=profile.employee).first()
        if task is None:
            return Response({'detail': 'Task not found.'}, status=404)
        task.status = request.data.get('status') or 'Completed'
        if 'completion_notes' in request.data:
            task.completion_notes = request.data.get('completion_notes') or ''
        if task.status == 'Completed' and not task.completed_at:
            task.completed_at = timezone.now()
        elif task.status != 'Completed':
            task.completed_at = None
        task.save(update_fields=['status', 'completion_notes', 'completed_at'])
        return Response(TaskSerializer(task).data)


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
