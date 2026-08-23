from rest_framework.permissions import SAFE_METHODS, BasePermission


def is_hr_or_legacy(request):
    """True for HR-role users, Admin (Django superusers), and pre-existing
    accounts that predate the role system (no profile row at all) — a
    missing profile means "full access", never "no access", so nothing that
    worked before this feature shipped starts failing."""
    if request.user.is_superuser:
        return True
    profile = getattr(request.user, 'profile', None)
    return profile is None or profile.role == 'HR'


def owner_scope_id(request):
    """The tenant id every owner-scoped row should be filtered/written
    against. Multiple logins (HR, IT Manager, Finance Admin, Department
    Head, Recruiter, Employee) now share one Organization, so `owner` can
    no longer mean "the currently authenticated user" — it has to mean "the
    org founder's user id" (UserProfile.data_owner_id) for every one of
    them. Falls back to the caller's own id for legacy accounts with no
    profile row, preserving today's behavior exactly for those."""
    profile = getattr(request.user, 'profile', None)
    return profile.data_owner_id if profile is not None else request.user.id


def _role_is(request, role):
    profile = getattr(request.user, 'profile', None)
    return bool(profile and profile.role == role)


class IsOwner(BasePermission):
    """Every per-user object across every module app is scoped to the
    tenant (organization) that created it — this is the entire
    authorization model, shared rather than duplicated per app. Also gates
    every action (list/create/etc, via has_permission) to HR-role accounts
    — Employee-role logins get none of the full CRUD modules, only the
    narrow self-service endpoints in core/my_views.py."""

    def has_permission(self, request, view):
        return is_hr_or_legacy(request)

    def has_object_permission(self, request, view, obj):
        return obj.owner_id == owner_scope_id(request)


class IsHR(BasePermission):
    """For the handful of viewsets that scope ownership through a parent
    object instead of their own `owner` field (EmployeeDocument,
    SurveyResponse, Enrollment, OnboardingTask, OffboardingTask, and the
    read-only dashboard-summary views) — same HR-only gate as IsOwner,
    without the object-level owner check those don't need."""

    def has_permission(self, request, view):
        return is_hr_or_legacy(request)


class IsITManager(BasePermission):
    """Full access to IT & Asset Management — same tier as IsOwner/IsHR,
    just gated to the IT Manager role instead. Always OR'd alongside
    IsOwner/IsHR, never used alone."""

    def has_permission(self, request, view):
        return _role_is(request, 'IT Manager')

    def has_object_permission(self, request, view, obj):
        return obj.owner_id == owner_scope_id(request)


class IsFinanceAdmin(BasePermission):
    """Full access to Payroll & Benefits — same tier as IsOwner/IsHR, just
    gated to the Finance Admin role instead."""

    def has_permission(self, request, view):
        return _role_is(request, 'Finance Admin')

    def has_object_permission(self, request, view, obj):
        return obj.owner_id == owner_scope_id(request)


class IsFinanceAdminReadOnly(BasePermission):
    """Finance Admin's narrow slice of People Management — read-only
    AttendanceRecord, to inform payroll/overtime calculations. Never a
    write: attendance itself stays HR/Department Head territory."""

    def has_permission(self, request, view):
        return _role_is(request, 'Finance Admin') and request.method in SAFE_METHODS

    def has_object_permission(self, request, view, obj):
        return obj.owner_id == owner_scope_id(request)


class IsRecruiter(BasePermission):
    """Full access to EVO-Recruit — same tier as IsOwner/IsHR, just gated
    to the Recruiter role instead."""

    def has_permission(self, request, view):
        return _role_is(request, 'Recruiter')

    def has_object_permission(self, request, view, obj):
        return obj.owner_id == owner_scope_id(request)


class IsAuditorReadOnly(BasePermission):
    """Auditor: "read-everywhere, write-nowhere across all modules — a
    compliance constraint, not a permission tier" (Control Hierarchy
    Matrix, role definitions). Org-wide, not scoped to any department/team
    — for viewsets/summary views where that blanket read grant is the
    whole story; see core.access_matrix for rows where Auditor's access
    needs to compose with other roles' finer-grained scoping instead."""

    def has_permission(self, request, view):
        return _role_is(request, 'Auditor') and request.method in SAFE_METHODS

    def has_object_permission(self, request, view, obj):
        return obj.owner_id == owner_scope_id(request)


def _department_of(obj):
    """Most department-scoped models hang an `employee` FK off the row;
    Employee itself carries `department` directly."""
    dept = getattr(obj, 'department', None)
    if dept is None and hasattr(obj, 'employee_id'):
        dept = obj.employee.department
    return dept


class IsDepartmentHead(BasePermission):
    """Base Department Head check — role match + same tenant + same
    department. Concrete narrower classes below (read-only / create-only /
    write) compose this same object-level shape with a different
    has_permission method-restriction."""

    def has_permission(self, request, view):
        return _role_is(request, 'Department Head')

    def has_object_permission(self, request, view, obj):
        profile = request.user.profile
        return obj.owner_id == owner_scope_id(request) and _department_of(obj) == profile.department


class IsDepartmentHeadReadOnly(BasePermission):
    """Department Head's view-only, department-filtered access — Employee/
    Attendance/Shift/SurveyResponse/Recognition in People; Goal/
    CompetencyRating/CareerPath/SuccessionPlan in Talent; BenefitEnrollment/
    BenefitClaim/TaxProfile/BankAccount in Payroll & Benefits."""

    def has_permission(self, request, view):
        return _role_is(request, 'Department Head') and request.method in SAFE_METHODS

    def has_object_permission(self, request, view, obj):
        return obj.owner_id == owner_scope_id(request) and _department_of(obj) == request.user.profile.department


class IsDepartmentHeadCreateOnly(BasePermission):
    """LeaveRequest/PromotionRequest (People) and SupportTicket/
    AssetIncident (IT) — Department Head may create (a "request") and
    list/retrieve what exists, but never update/delete. This absence of an
    update right *is* the approval gate: only HR/IT Manager can act on what
    a Department Head creates."""

    def has_permission(self, request, view):
        if not _role_is(request, 'Department Head'):
            return False
        return request.method in (*SAFE_METHODS, 'POST')

    def has_object_permission(self, request, view, obj):
        return obj.owner_id == owner_scope_id(request) and _department_of(obj) == request.user.profile.department


class IsDepartmentHeadWrite(BasePermission):
    """Goal/CompetencyRating/CareerPath — working tools, not employment-
    status changes, so Department Head gets full create+update (no approval
    gate) for their own department's employees."""

    def has_permission(self, request, view):
        return _role_is(request, 'Department Head') and request.method != 'DELETE'

    def has_object_permission(self, request, view, obj):
        return obj.owner_id == owner_scope_id(request) and _department_of(obj) == request.user.profile.department


class IsDepartmentHeadAppraisalAccess(BasePermission):
    """Appraisal — Department Head may create/update (drafting/submitting),
    but the view's perform_update guard separately blocks them from ever
    setting status='Finalized' — that step stays HR/Admin-only, mirroring
    the PayrollRun 'Reconciled' pattern."""

    def has_permission(self, request, view):
        return _role_is(request, 'Department Head') and request.method != 'DELETE'

    def has_object_permission(self, request, view, obj):
        return obj.owner_id == owner_scope_id(request) and obj.employee.department == request.user.profile.department


class IsDepartmentHeadRequisitionAccess(BasePermission):
    """Requisition — Department Head views every requisition (org-wide,
    not department-scoped — matches "view recruit") and can create new ones
    ("request for recruit"), but never updates/deletes an existing one."""

    def has_permission(self, request, view):
        if not _role_is(request, 'Department Head'):
            return False
        return request.method in (*SAFE_METHODS, 'POST')

    def has_object_permission(self, request, view, obj):
        return obj.owner_id == owner_scope_id(request)


class IsITManagerTaskAccess(BasePermission):
    """OnboardingTask/OffboardingTask — IT Manager's narrow "device tasks"
    slice of the employee lifecycle: only rows in the Device Assignment /
    Hardware Clearance categories, view + update, never create/delete
    (those checklists are created by the onboarding/offboarding flow
    itself, not by IT)."""

    DEVICE_CATEGORIES = {'Device Assignment', 'Hardware Clearance'}

    def has_permission(self, request, view):
        if not _role_is(request, 'IT Manager'):
            return False
        return request.method in (*SAFE_METHODS, 'PUT', 'PATCH')

    def has_object_permission(self, request, view, obj):
        parent = getattr(obj, 'onboarding', None) or getattr(obj, 'offboarding', None)
        return (
            obj.category in self.DEVICE_CATEGORIES
            and parent is not None
            and parent.owner_id == owner_scope_id(request)
        )
