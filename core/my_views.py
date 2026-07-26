from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from people.models import AttendanceRecord
from people.serializers import EmployeeLiteSerializer
from talent.models import Goal
from talent.serializers import GoalSerializer

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
