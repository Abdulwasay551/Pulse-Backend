import uuid

from django.conf import settings
from django.db import models


class Organization(models.Model):
    """The "company" an HR account sets up — every Employee-role account
    joins one of these (their inviting HR's). Data ownership itself still
    keys off the HR user's own id (see UserProfile.data_owner_id) rather
    than switching every module's `owner` FK to point at Organization —
    that would mean touching every model in Recruit/People/Talent/Payroll
    for no functional gain, since one HR account = one organization today
    (no multi-HR orgs yet)."""

    name = models.CharField(max_length=200)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='organizations_created')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    """Role + organization membership for a login. Multiple logins now
    share one Organization — an HR founder plus whichever of IT Manager/
    Finance Admin/Department Head/Recruiter/Employee accounts they (or an
    Admin, i.e. a Django superuser) have created for it. Public self-signup
    is invite-only for now (see RegisterSerializer), so every profile here
    traces back to either the original founder or an explicit HR/Admin
    provisioning action.

    Pre-existing users (created before this feature shipped) have no
    profile row at all — every permission/role check here treats a missing
    profile as "HR, full access", so nothing existing breaks."""

    ROLE_CHOICES = [
        ('HR', 'HR'),
        ('Employee', 'Employee'),
        ('IT Manager', 'IT Manager'),
        ('Finance Admin', 'Finance Admin'),
        ('Department Head', 'Department Head'),
        ('Recruiter', 'Recruiter'),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='HR')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='members')
    # Which people.Employee record this login *is* — only ever set for
    # Employee-role profiles, used to scope clock-in/goals/etc to "me".
    employee = models.ForeignKey(
        'people.Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='user_accounts'
    )
    # Only ever set for Department Head profiles — scopes their read/write
    # access to Employee.department == this value. Free-text, matching
    # Employee.department exactly (no normalized Department model exists).
    department = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user.username} ({self.role})'

    @property
    def data_owner_id(self):
        """The user id whose owner-scoped rows (Candidate, Employee,
        PayrollRun, etc.) this profile's organization shares — the HR
        founder's own id, for both HR and Employee profiles alike."""
        return self.organization.created_by_id


class EmployeeInvite(models.Model):
    """A pending "join this organization" email invite for a specific
    people.Employee record — consumed by RegisterSerializer when someone
    signs up with ?invite=<token>."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='invites')
    employee = models.ForeignKey('people.Employee', on_delete=models.CASCADE, related_name='invites')
    email = models.EmailField()
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'Invite for {self.employee.name} ({self.email})'


class ActivityLog(models.Model):
    """A cross-module activity feed entry — any module app can write to this
    (see core.activity.log_activity) so a user's dashboard can show one
    unified "recent activity" list regardless of which module the action
    happened in."""

    TONE_CHOICES = [
        ('primary', 'primary'),
        ('amber', 'amber'),
        ('maroon', 'maroon'),
        ('neutral', 'neutral'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='activity_log')
    message = models.CharField(max_length=255)
    tone = models.CharField(max_length=10, choices=TONE_CHOICES, default='neutral')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.message


class Announcement(models.Model):
    """An HR-authored notice shown alongside ActivityLog entries in the main
    HR dashboard's "Recent activity" feed (see core.views.AnnouncementViewSet)
    — unlike ActivityLog, these are written directly by a user rather than
    generated as a side effect of some other action."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='announcements')
    message = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.message


class DemoRequest(models.Model):
    """A submission of the public "Book a Demo" form."""

    full_name = models.CharField(max_length=150)
    email = models.EmailField()
    contact_number = models.CharField(max_length=30)
    business_name = models.CharField(max_length=150)
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.full_name} ({self.business_name})'
