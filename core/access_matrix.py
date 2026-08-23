"""Generic, matrix-driven permission engine for the Pulse HCM "Control
Hierarchy Matrix" (role x sub-module x R/W/A/RWA, with '*' meaning "own
record only" and MGR meaning "own team, resolved from the live org
chart"). Encodes each matrix row as data — `matrix_permission(...)` plus
`scoped_queryset(...)` — instead of a hand-written permission class per
row, since the full matrix spans 5 modules and dozens of rows.

Deliberately additive, never a replacement: every viewset keeps its
existing IsOwner/IsHR/IsDepartmentHead* classes exactly as they are (OR'd
together in permission_classes, the same composition pattern already used
everywhere), and adds a matrix_permission(...) alongside them. Department
Head keeps its own dedicated classes and is intentionally absent from
ROLE_CODE below — the matrix doesn't define a Department Head column, and
this engine should never grant that role anything beyond what its existing
classes already do.
"""

from rest_framework.permissions import BasePermission

from .permissions import owner_scope_id

# UserProfile.role -> this matrix's column code. Department Head has no
# entry on purpose (see module docstring).
ROLE_CODE = {
    'HR': 'HRA',
    'IT Manager': 'ITA',
    'Finance Admin': 'FA',
    'Recruiter': 'REC',
    'Employee': 'EMP',
    'Contractor': 'CON',
    'Auditor': 'AUD',
}


def role_code(request):
    """SA for Django superusers *and* legacy no-profile accounts (same
    "missing profile = full access, nothing existing breaks" convention as
    core.permissions.is_hr_or_legacy — a pre-role-system account predates
    the matrix entirely and reads as the org's unrestricted root user, not
    as a modern HRA hire whose access the matrix deliberately scopes to
    Recruit/People/Talent only), else the matrix column for this login's
    role — or None for a role the matrix doesn't define a column for
    (Department Head)."""
    if request.user.is_superuser:
        return 'SA'
    profile = getattr(request.user, 'profile', None)
    if profile is None:
        return 'SA'
    return ROLE_CODE.get(profile.role)


def _manager_descendant_ids(employee_id, _seen=None):
    """Every direct + indirect report of `employee_id`, walking
    Employee.manager down the live org chart. `_seen` guards a manager
    cycle from infinite-looping a request (shouldn't exist, but a
    corrupted chart shouldn't be able to hang the API)."""
    from people.models import Employee

    if _seen is None:
        _seen = set()
    direct = list(Employee.objects.filter(manager_id=employee_id).values_list('id', flat=True))
    ids = set(direct)
    for child_id in direct:
        if child_id in _seen:
            continue
        _seen.add(child_id)
        ids |= _manager_descendant_ids(child_id, _seen)
    return ids


def is_manager_of(request, employee_id):
    """True if `employee_id` is anywhere among the caller's direct/indirect
    reports — MGR is a dynamic capability any login with reports has,
    independent of their assigned role string."""
    profile = getattr(request.user, 'profile', None)
    if profile is None or not profile.employee_id or employee_id is None:
        return False
    return employee_id in _manager_descendant_ids(profile.employee_id)


def has_any_reports(request):
    """List/create-level stand-in for "does the MGR column apply to this
    login at all" — row-level scoping still happens via is_manager_of /
    scoped_queryset."""
    profile = getattr(request.user, 'profile', None)
    if profile is None or not profile.employee_id:
        return False
    from people.models import Employee

    return Employee.objects.filter(manager_id=profile.employee_id).exists()


_METHOD_LETTER = {
    'GET': 'R', 'HEAD': 'R', 'OPTIONS': 'R',
    'POST': 'W', 'PUT': 'W', 'PATCH': 'W', 'DELETE': 'W',
}


def _covers(code, letter):
    """'RWA' contains R/W/A; 'R*' contains only R. An 'A' (Approve) is
    always treated as covering both read and write — approving something
    means reading it and then PATCHing its status, and REST has no verb
    that means "write, but only a status transition"; if a view needs to
    stop an Approve-only grant from editing unrelated fields, that's a
    perform_update-level guard, the same pattern this codebase's existing
    Department-Head-approval classes already use (see
    IsDepartmentHeadAppraisalAccess), not something this permission class
    itself enforces."""
    if not code or code == '-':
        return False
    if 'A' in code:
        return True
    return letter in code


def _default_owner_getter(obj):
    return getattr(obj, 'owner_id', None)


def _default_self_id(request):
    profile = getattr(request.user, 'profile', None)
    return profile.employee_id if profile else None


def resolve_attr_path(obj, path):
    """Follows a Django-style `a__b__c` attribute path off a model
    instance — the has_object_permission counterpart to the `__` lookups
    scoped_queryset already passes straight through to the ORM. A plain
    name with no `__` (every existing caller, before Recruit) behaves
    exactly like a bare getattr. Needed for matrix rows two hops from
    "whose record is this" — e.g. Recruit's OnboardingTask, which only
    reaches its candidate via `onboarding.candidate_id`."""
    value = obj
    for part in path.split('__'):
        if value is None:
            return None
        value = getattr(value, part, None)
    return value


def matrix_permission(*, self_scope_field='employee_id', owner_getter=_default_owner_getter, self_id_getter=None, **codes):
    """Builds a DRF permission class from one matrix row, e.g.:

        matrix_permission(aud='R', mgr='R*', emp='RW*', con='RW*')

    Unspecified roles default to no access. `self_scope_field` names the
    attribute (or `a__b` path, see resolve_attr_path) holding "whose record
    is this" (default `employee_id`; pass `id` for a model that *is* the
    employee row). `owner_getter` resolves the tenant id for models without
    a direct `owner` field (e.g. `lambda obj: obj.survey.owner_id`);
    returning None skips the tenant check (only safe when the viewset's own
    queryset already scopes it).

    `self_id_getter(request)` resolves the value that should match
    `self_scope_field` on "your own" row — defaults to the caller's
    `profile.employee_id`, right for any model keyed directly by Employee.
    Pass a custom resolver for a model reachable only via a reverse link —
    e.g. Recruit's Candidate-keyed rows, where "yours" means
    `profile.employee.source_candidate_id`, not `profile.employee_id`
    itself. Note: MGR's object-level branch below always treats
    `self_scope_field`'s value as an Employee id (via is_manager_of) — don't
    pair `mgr=...` here with a non-Employee-keyed self_scope_field/
    self_id_getter; use a dedicated permission class instead for that case
    (see recruit.permissions.manager_candidate_access).
    """

    codes_norm = {k.upper(): v for k, v in codes.items()}
    get_self_id = self_id_getter or _default_self_id

    class _MatrixPermission(BasePermission):
        def has_permission(self, request, view):
            letter = _METHOD_LETTER.get(request.method, 'W')
            code = codes_norm.get(role_code(request))
            if _covers(code, letter):
                return True
            mgr_code = codes_norm.get('MGR')
            if mgr_code and mgr_code != '-' and has_any_reports(request):
                return _covers(mgr_code, letter)
            return False

        def has_object_permission(self, request, view, obj):
            owner_id = owner_getter(obj)
            if owner_id is not None and owner_id != owner_scope_id(request):
                return False

            letter = _METHOD_LETTER.get(request.method, 'W')
            target_id = resolve_attr_path(obj, self_scope_field)

            code = codes_norm.get(role_code(request))
            if _covers(code, letter):
                if '*' not in code:
                    return True
                self_id = get_self_id(request)
                if self_id is not None and self_id == target_id:
                    return True
                # Own-role code exists but this object isn't "my own record"
                # — deliberately falls through to the MGR check below rather
                # than returning False here. A manager is very often *also*
                # an Employee-role login with its own starred EMP grant on
                # this same row (e.g. Attendance: EMP='R*' on their own
                # timesheet), and MGR is a capability layered on top of
                # whatever base role someone has, not a separate exclusive
                # tier — stopping at "this isn't your own record" would deny
                # a manager access to their reports' rows entirely.

            # MGR is always team-scoped per its role definition ("scoped to
            # direct and indirect reports") regardless of whether the matrix
            # cell happens to carry a '*' — the doc isn't consistent about
            # marking it, but the role description is unconditional.
            mgr_code = codes_norm.get('MGR')
            if mgr_code and _covers(mgr_code, letter) and target_id is not None:
                return is_manager_of(request, target_id)

            return False

    return _MatrixPermission


def scoped_queryset(request, base_qs, *, self_scope_field='employee_id', self_id_getter=None, **codes):
    """Narrows a queryset to what the caller's matrix row allows — pairs
    with matrix_permission (pass the *same* role codes, self_scope_field,
    and self_id_getter to both). Call this from get_queryset() *after* any
    existing tenant/Department-Head filtering; it only ever narrows further,
    and returns `.none()` for a role the row doesn't mention at all.
    HR/IT Manager/Finance Admin/Department Head's existing broader access
    should be handled by the caller *before* reaching this — see the
    "already has full access" early-return pattern in each updated
    get_queryset(). See matrix_permission for what `self_id_getter` is for;
    the same "don't pair mgr= with a non-Employee-keyed self_scope_field"
    caveat applies to the MGR branch below.
    """
    codes_norm = {k.upper(): v for k, v in codes.items()}
    rc = role_code(request)
    code = codes_norm.get(rc)
    get_self_id = self_id_getter or _default_self_id

    # Own-record and own-team access are additive, not exclusive — a
    # manager is very often *also* an Employee-role login with its own
    # starred EMP grant on this row, and MGR layers on top of that rather
    # than replacing it (see the matching comment in matrix_permission's
    # has_object_permission). Build up every filter that applies, then
    # union them, instead of returning on whichever check matches first.
    scopes = []

    if code and code != '-':
        if '*' not in code:
            return base_qs
        self_id = get_self_id(request)
        if self_id:
            scopes.append({self_scope_field: self_id})

    mgr_code = codes_norm.get('MGR')
    if mgr_code and mgr_code != '-':
        profile = getattr(request.user, 'profile', None)
        if profile and profile.employee_id:
            ids = _manager_descendant_ids(profile.employee_id)
            if ids:
                scopes.append({f'{self_scope_field}__in': ids})

    if not scopes:
        return base_qs.none()
    if len(scopes) == 1:
        return base_qs.filter(**scopes[0])

    from functools import reduce
    from django.db.models import Q

    return base_qs.filter(reduce(lambda a, b: a | b, (Q(**s) for s in scopes)))
