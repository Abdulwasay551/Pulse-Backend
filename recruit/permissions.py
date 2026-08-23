"""Recruit-specific permission pieces that don't fit core.access_matrix's
generic matrix_permission/scoped_queryset shape, plus small helpers shared
across recruit/views.py.

Two shapes of gap show up in the Control Hierarchy Matrix's Recruit rows,
neither of which the generic engine (built and proven on People, where
every model is keyed directly by Employee) handles out of the box:

1. "Own record" scoping for Employee/Contractor, where the row's model is
   keyed by Candidate, not Employee. There is no forward FK from a
   Candidate/Onboarding/Offboarding row to "the employee logged in right
   now" — only the reverse link, people.Employee.source_candidate (set once
   a candidate is actually hired). `_my_candidate_id` resolves that reverse
   link for use as a `self_id_getter` with core.access_matrix's
   matrix_permission/scoped_queryset.

2. MGR ("own team") scoping for rows whose model has no FK to a specific
   manager/employee at all:
   - Requisition/Candidate/OfferLetter — Requisition.hiring_manager is a
     free-text label, not an Employee FK, and Candidate/OfferLetter carry no
     manager assignment whatsoever. There's no data to scope by, so
     `manager_broad_access` approximates MGR as tenant-wide access for any
     login that actually has reports — the same kind of approximation the
     migration brief explicitly sanctions for the Client row's "assigned
     clients" concept, rather than blocking on a new assignment feature.
   - Onboarding/Offboarding (and their per-category task rows) — these
     *can* be scoped precisely, but only by walking backwards through
     Employee.source_candidate to find the employee (if any) this candidate
     became, then checking the live org chart — `manager_candidate_access`
     does that real reverse-lookup scoping.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from core.access_matrix import has_any_reports, is_manager_of, resolve_attr_path
from core.permissions import owner_scope_id


def _my_candidate_id(request):
    """The Candidate row this Employee/Contractor login "is", via
    people.Employee.source_candidate — None for any other role, for an
    Employee/Contractor login with no linked employee record, or for one
    whose Employee record wasn't sourced from a Candidate at all (added to
    People directly rather than hired through EVO-Recruit)."""
    profile = getattr(request.user, 'profile', None)
    if not profile or not profile.employee_id:
        return None
    return profile.employee.source_candidate_id


def _employee_id_for_candidate(candidate_id):
    """The people.Employee row (if any) this candidate became — the reverse
    of Employee.source_candidate. None if they never got hired (or the
    Employee row was deleted/reassigned since)."""
    if candidate_id is None:
        return None
    from people.models import Employee

    return Employee.objects.filter(source_candidate_id=candidate_id).values_list('id', flat=True).first()


def manager_candidate_ids(request):
    """Every candidate id whose sourced Employee is among the caller's
    direct/indirect reports — the queryset-level counterpart to
    manager_candidate_access's per-object reverse lookup, for get_queryset()
    to filter Onboarding/Offboarding/*Task rows by."""
    profile = getattr(request.user, 'profile', None)
    if not profile or not profile.employee_id:
        return []
    from core.access_matrix import _manager_descendant_ids
    from people.models import Employee

    report_ids = _manager_descendant_ids(profile.employee_id)
    if not report_ids:
        return []
    return list(
        Employee.objects.filter(id__in=report_ids, source_candidate_id__isnull=False)
        .values_list('source_candidate_id', flat=True)
    )


def manager_broad_access(methods):
    """Approximates MGR for Requisition/Candidate/OfferLetter (see module
    docstring, gap #2) — tenant-wide access at the given HTTP methods for
    any login that is actually a manager (has direct/indirect reports; MGR
    is a dynamic capability, not a stored role), since none of these models
    carry data to scope more precisely by. `methods` should be SAFE_METHODS
    for a plain read-only ('R*') row, or `(*SAFE_METHODS, 'PUT', 'PATCH')`
    for an approve ('A*') row — never include POST/DELETE, since MGR is
    never the one creating/deleting these rows in the matrix."""

    class _ManagerBroadAccess(BasePermission):
        def has_permission(self, request, view):
            return has_any_reports(request) and request.method in methods

        def has_object_permission(self, request, view, obj):
            return getattr(obj, 'owner_id', None) == owner_scope_id(request)

    return _ManagerBroadAccess


def manager_candidate_access(*, candidate_field='candidate_id', methods=SAFE_METHODS, categories=None):
    """Real "own team" MGR scoping for a Recruit row keyed (directly, or via
    one `a__b` hop) by Candidate — Onboarding/Offboarding and their
    per-category task rows (see module docstring, gap #2). `candidate_field`
    names that path (e.g. `'candidate_id'` for Onboarding/Offboarding
    themselves, `'onboarding__candidate_id'` for OnboardingTask).
    `categories`, if given, further restricts object-level access to task
    rows of those categories only (irrelevant for Onboarding/Offboarding
    themselves, which have no `category` field)."""

    class _ManagerCandidateAccess(BasePermission):
        def has_permission(self, request, view):
            return has_any_reports(request) and request.method in methods

        def has_object_permission(self, request, view, obj):
            if categories is not None and getattr(obj, 'category', None) not in categories:
                return False
            candidate_id = resolve_attr_path(obj, candidate_field)
            employee_id = _employee_id_for_candidate(candidate_id)
            return employee_id is not None and is_manager_of(request, employee_id)

    return _ManagerCandidateAccess


class IsSelfOnboardingTaskAccess(BasePermission):
    """Employee/Contractor's own onboarding checklist (OnboardingTask) —
    access varies by category per the Control Hierarchy Matrix:

        Joining Documentation:  EMP W*   CON W*
        Orientation:            EMP R*   CON R*
        Training Plan:          EMP RW*  CON R*
        Portal Access:          EMP R*   CON R*
        Probation Evaluation:   EMP R*   CON —   (contractors aren't evaluated)
        Device Assignment:      EMP R*   CON R*

    "Own" is resolved via _my_candidate_id (people.Employee.source_candidate)
    since OnboardingTask is keyed by Candidate, not Employee — the generic
    matrix_permission's employee_id-based self-scoping doesn't apply here.
    Never grants create/delete — the checklist itself is created by the
    onboarding flow, not by the new hire."""

    EMP_CODES = {
        'Joining Documentation': 'W', 'Orientation': 'R', 'Training Plan': 'RW',
        'Portal Access': 'R', 'Probation Evaluation': 'R', 'Device Assignment': 'R',
    }
    CON_CODES = {
        'Joining Documentation': 'W', 'Orientation': 'R', 'Training Plan': 'R',
        'Portal Access': 'R', 'Device Assignment': 'R',
    }

    def has_permission(self, request, view):
        profile = getattr(request.user, 'profile', None)
        if not profile or profile.role not in ('Employee', 'Contractor') or not profile.employee_id:
            return False
        return request.method in (*SAFE_METHODS, 'PUT', 'PATCH')

    def has_object_permission(self, request, view, obj):
        profile = request.user.profile
        candidate_id = _my_candidate_id(request)
        if candidate_id is None or obj.onboarding.candidate_id != candidate_id:
            return False
        if obj.onboarding.owner_id != owner_scope_id(request):
            return False
        codes = self.EMP_CODES if profile.role == 'Employee' else self.CON_CODES
        code = codes.get(obj.category)
        if not code:
            return False
        letter = 'R' if request.method in SAFE_METHODS else 'W'
        return letter in code


class IsITManagerAccessStatusAccess(BasePermission):
    """IT Manager also gets full RWA on Access Status offboarding tasks
    (revoking system/tool access when someone leaves) — core.permissions'
    shared IsITManagerTaskAccess only covers Device Assignment/Hardware
    Clearance, so this is a small Recruit-local supplement for the
    newly-added Access Status row rather than editing that shared class."""

    def has_permission(self, request, view):
        from core.permissions import _role_is

        return _role_is(request, 'IT Manager')

    def has_object_permission(self, request, view, obj):
        return obj.category == 'Access Status' and obj.offboarding.owner_id == owner_scope_id(request)


class IsFinanceAdminHardwareClearanceReadOnly(BasePermission):
    """Finance Admin sees asset value/write-off impact on Hardware Clearance
    offboarding tasks only (Control Hierarchy Matrix: FA=R here, unlike
    every other Offboarding row, where FA='-')."""

    def has_permission(self, request, view):
        from core.permissions import _role_is

        return _role_is(request, 'Finance Admin') and request.method in SAFE_METHODS

    def has_object_permission(self, request, view, obj):
        return obj.category == 'Hardware Clearance' and obj.offboarding.owner_id == owner_scope_id(request)
