from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from people.models import Employee

from .models import EmployeeInvite, Organization, UserProfile
from .permissions import IsHR

User = get_user_model()


def get_or_create_hr_profile(user):
    """Every HR feature (invites, direct account creation) needs the
    requesting user's Organization — pre-existing HR accounts (created
    before this feature shipped) have no profile row yet, so this creates
    one lazily on first use instead of requiring a backfill migration."""
    profile = getattr(user, 'profile', None)
    if profile is not None:
        return profile
    org = Organization.objects.create(name=f"{user.username}'s organization", created_by=user)
    return UserProfile.objects.create(user=user, role='HR', organization=org)


class EmployeeInviteView(APIView):
    """HR sends an email invite for one of their people.Employee records to
    self-register a login. The signup itself is consumed by
    RegisterSerializer via ?invite=<token>."""

    permission_classes = [IsAuthenticated, IsHR]

    def post(self, request):
        employee_id = request.data.get('employee')
        email = request.data.get('email', '').strip()
        if not employee_id or not email:
            return Response({'detail': 'employee and email are required.'}, status=status.HTTP_400_BAD_REQUEST)

        employee = get_object_or_404(Employee, id=employee_id, owner=request.user)
        profile = get_or_create_hr_profile(request.user)

        invite = EmployeeInvite.objects.create(
            organization=profile.organization, employee=employee, email=email
        )
        signup_link = f'{settings.FRONTEND_URL}/signup?invite={invite.token}'
        send_mail(
            subject=f'You’re invited to join {profile.organization.name} on EvoHR',
            message=(
                f'{employee.name}, you’ve been invited to set up your employee account for '
                f'{profile.organization.name}.\n\nCreate your login here: {signup_link}\n\n'
                f'If you weren’t expecting this, you can safely ignore this email.'
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=True,
        )
        return Response({'detail': 'Invite sent.', 'signup_link': signup_link})


class InviteDetailView(APIView):
    """Public — the signup page reads this (via ?invite=<token>) to
    prefill the email and show which organization/employee this invite is
    for."""

    permission_classes = [AllowAny]

    def get(self, request, token):
        invite = get_object_or_404(EmployeeInvite, token=token, accepted_at__isnull=True)
        return Response(
            {
                'email': invite.email,
                'organization': invite.organization.name,
                'employee_name': invite.employee.name,
            }
        )


class EmployeeAccountCreateView(APIView):
    """HR sets a username/password directly for one of their employees —
    no email/self-signup step. Creates the login immediately."""

    permission_classes = [IsAuthenticated, IsHR]

    def post(self, request):
        employee_id = request.data.get('employee')
        username = request.data.get('username', '').strip()
        password = request.data.get('password', '')
        if not employee_id or not username or not password:
            return Response({'detail': 'employee, username, and password are required.'}, status=status.HTTP_400_BAD_REQUEST)

        employee = get_object_or_404(Employee, id=employee_id, owner=request.user)
        if hasattr(employee, 'user_accounts') and employee.user_accounts.exists():
            return Response({'detail': 'This employee already has a login.'}, status=status.HTTP_400_BAD_REQUEST)
        if User.objects.filter(username__iexact=username).exists():
            return Response({'username': ['That username is already taken.']}, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_password(password)
        except DjangoValidationError as exc:
            return Response({'password': list(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)

        profile = get_or_create_hr_profile(request.user)
        user = User.objects.create_user(username=username, email=employee.email, password=password)
        UserProfile.objects.create(user=user, role='Employee', organization=profile.organization, employee=employee)

        return Response({'detail': 'Account created.', 'username': username}, status=status.HTTP_201_CREATED)
