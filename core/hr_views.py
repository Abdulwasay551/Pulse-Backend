from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations.email_provider import EmailProviderError, has_working_email, send_org_email
from people.models import Employee

from .models import EmployeeInvite, Organization, UserProfile
from .permissions import IsHR, owner_scope_id

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

        uid = owner_scope_id(request)
        # HR is standing right here watching this action, unlike a public
        # password-reset request — so rather than silently "succeeding"
        # with an email that goes nowhere (console backend delivers
        # nothing), refuse up front and point them at the fix.
        if not has_working_email(uid):
            return Response(
                {
                    'detail': 'No email provider connected — connect one to actually send invites.',
                    'code': 'smtp_not_configured',
                },
                status=status.HTTP_409_CONFLICT,
            )

        employee = get_object_or_404(Employee, id=employee_id, owner_id=uid)
        profile = get_or_create_hr_profile(request.user)

        invite = EmployeeInvite.objects.create(
            organization=profile.organization, employee=employee, email=email
        )
        signup_link = f'{settings.FRONTEND_URL}/signup?invite={invite.token}'
        try:
            send_org_email(
                uid,
                subject=f'You’re invited to join {profile.organization.name} on Pulse',
                message=(
                    f'{employee.name}, you’ve been invited to set up your employee account for '
                    f'{profile.organization.name}.\n\nCreate your login here: {signup_link}\n\n'
                    f'If you weren’t expecting this, you can safely ignore this email.'
                ),
                recipient_list=[email],
                fail_silently=False,
            )
        except EmailProviderError as exc:
            invite.delete()
            return Response(
                {'detail': f'Could not send the invite: {exc}', 'code': 'smtp_send_failed'},
                status=status.HTTP_502_BAD_GATEWAY,
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


ROLES_HR_CAN_CREATE = {'Employee', 'Department Head', 'Recruiter'}


class EmployeeAccountCreateView(APIView):
    """HR sets a username/password directly for one of their employees —
    no email/self-signup step. Creates the login immediately.

    Also doubles as the provisioning endpoint for Department Head and
    Recruiter accounts (same shape: an existing Employee record gets a
    login), since duplicating the username/password validation in a
    separate view would be pure repetition. IT Manager/Finance Admin are
    deliberately NOT accepted here — those are Admin (superuser)-only,
    provisioned via Django admin instead."""

    permission_classes = [IsAuthenticated, IsHR]

    def post(self, request):
        employee_id = request.data.get('employee')
        username = request.data.get('username', '').strip()
        password = request.data.get('password', '')
        role = request.data.get('role', 'Employee')
        department = request.data.get('department', '').strip()
        if not employee_id or not username or not password:
            return Response({'detail': 'employee, username, and password are required.'}, status=status.HTTP_400_BAD_REQUEST)
        if role not in ROLES_HR_CAN_CREATE:
            return Response(
                {'role': ['Invalid role — must be Employee, Department Head, or Recruiter.']},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if role == 'Department Head' and not department:
            return Response(
                {'department': ['department is required for a Department Head account.']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        employee = get_object_or_404(Employee, id=employee_id, owner_id=owner_scope_id(request))
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
        UserProfile.objects.create(
            user=user, role=role, organization=profile.organization, employee=employee,
            department=department if role == 'Department Head' else '',
        )

        return Response({'detail': 'Account created.', 'username': username, 'role': role}, status=status.HTTP_201_CREATED)


# Every storable UserProfile role a Super Admin can hand out directly.
# UserProfile.clean() itself only hard-requires an Employee link for
# Employee/Contractor — every other role here may optionally attach one
# for context (e.g. Department Head's department scoping) but doesn't
# need to.
ROLES_ADMIN_CAN_CREATE = {
    'HR', 'Employee', 'IT Manager', 'Finance Admin', 'Department Head',
    'Recruiter', 'Auditor', 'Contractor',
}
ROLES_REQUIRING_EMPLOYEE = {'Employee', 'Contractor'}


class AdminAccountCreateView(APIView):
    """Super Admin (Django superuser) provisioning — creates a login for
    any storable role directly, same "set a username/password, no email
    step" shape as EmployeeAccountCreateView above. That view is HR's
    narrower self-service flow (Employee/Department Head/Recruiter only,
    always tied to an existing Employee record); this is the full-power
    version reachable from the Super Admin dashboard's "Invite / create
    user" panel — IT Manager/Finance Admin/Auditor accounts, previously
    only provisionable via Django admin per that view's own docstring,
    can now be created from the app itself."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.user.is_superuser:
            return Response(
                {'detail': 'Only a Super Admin account can create logins for these roles.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        username = request.data.get('username', '').strip()
        password = request.data.get('password', '')
        role = request.data.get('role', '')
        email = request.data.get('email', '').strip()
        employee_id = request.data.get('employee')
        department = request.data.get('department', '').strip()

        if not username or not password or not role:
            return Response({'detail': 'username, password, and role are required.'}, status=status.HTTP_400_BAD_REQUEST)
        if role not in ROLES_ADMIN_CAN_CREATE:
            return Response(
                {'role': [f'Invalid role — must be one of: {", ".join(sorted(ROLES_ADMIN_CAN_CREATE))}.']},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if role == 'Department Head' and not department:
            return Response(
                {'department': ['department is required for a Department Head account.']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        employee = None
        if employee_id:
            employee = get_object_or_404(Employee, id=employee_id, owner_id=owner_scope_id(request))
            if hasattr(employee, 'user_accounts') and employee.user_accounts.exists():
                return Response({'detail': 'This employee already has a login.'}, status=status.HTTP_400_BAD_REQUEST)
        elif role in ROLES_REQUIRING_EMPLOYEE:
            return Response(
                {'employee': [f'employee is required for a {role} account.']}, status=status.HTTP_400_BAD_REQUEST
            )

        if User.objects.filter(username__iexact=username).exists():
            return Response({'username': ['That username is already taken.']}, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_password(password)
        except DjangoValidationError as exc:
            return Response({'password': list(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)

        profile = get_or_create_hr_profile(request.user)
        user = User.objects.create_user(
            username=username, email=email or (employee.email if employee else ''), password=password
        )
        UserProfile.objects.create(
            user=user, role=role, organization=profile.organization, employee=employee,
            department=department if role == 'Department Head' else '',
        )

        return Response({'detail': 'Account created.', 'username': username, 'role': role}, status=status.HTTP_201_CREATED)
