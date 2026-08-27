"""Powers the public, unlinked /api-docs dev reference page — walks the
real URLconf of every Pulse-owned app so the directory can never drift
from what's actually registered (no hand-maintained endpoint list to go
stale). Deliberately public (AllowAny) and reachable only by URL, not
linked from any navigation — see the frontend page's own note."""

import importlib
import re

from django.urls import URLPattern, URLResolver
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

_NAMED_GROUP_RE = re.compile(r'\(\?P<(\w+)>[^)]*\)')
# DRF's DefaultRouter emits a plain path plus a near-duplicate ".<format>"
# suffixed variant (content-negotiation via URL, e.g. "connections.json") —
# noise for a human-facing directory, filtered out below by this literal
# substring rather than a precise regex, since the exact trailing
# punctuation (?/$ combinations) varies by route and isn't worth matching
# exactly for a simple exclusion check.
_FORMAT_SUFFIX_MARKER = '.(?P<format>'


def _clean_segment(raw: str) -> str:
    """Router-generated leaf patterns are regex (e.g.
    "^connections/(?P<pk>[^/.]+)/$") while hand-written path() segments are
    already clean route strings — strip regex anchors before concatenating
    with the (always-clean) prefix, since ^/$ only make sense stripped from
    the very start/end of this individual segment, not the joined path."""
    return re.sub(r'\$$', '', raw.lstrip('^'))


def _prettify_groups(path: str) -> str:
    return _NAMED_GROUP_RE.sub(lambda m: '{' + m.group(1) + '}', path)

_SECTIONS = [
    ('core.urls', 'Core / Auth', 'api/'),
    ('recruit.urls', 'Recruit', 'api/recruit/'),
    ('people.urls', 'People', 'api/people/'),
    ('talent.urls', 'Talent', 'api/talent/'),
    ('payroll_benefits.urls', 'Payroll & Benefits', 'api/payroll-benefits/'),
    ('it_assets.urls', 'IT & Assets', 'api/it-assets/'),
    ('ai_core.urls', 'AI', 'api/ai/'),
    ('integrations.urls', 'Integrations', 'api/integrations/'),
]


def _inspect_callback(callback):
    """Router-generated ViewSet endpoints carry an `actions` dict (set by
    ViewSet.as_view({...})) mapping http method -> viewset method name —
    read directly, no instantiation needed, for methods. Everything else
    (APIView, @api_view-wrapped functions) exposes `.cls`, which is safe
    to instantiate (constructors don't touch the DB) to read the same
    `allowed_methods` property DRF itself uses, plus permission_classes
    (whether AllowAny is present, i.e. genuinely public) and the class's
    own docstring as a real, non-fabricated description."""
    actions = getattr(callback, 'actions', None)
    if actions:
        methods = sorted(m.upper() for m in actions.keys())
    else:
        methods = []

    cls = getattr(callback, 'cls', None)
    auth_required = True
    description = ''
    if cls is not None:
        try:
            instance = cls()
            if not actions:
                methods = sorted(getattr(instance, 'allowed_methods', []))
            perm_classes = getattr(instance, 'permission_classes', [])
            auth_required = not any(getattr(p, '__name__', '') == 'AllowAny' for p in perm_classes)
        except Exception:
            pass
        # Collapse all whitespace (these docstrings wrap across lines) before
        # taking the first sentence — several views here have long,
        # multi-paragraph docstrings written for future maintainers, not
        # this directory, and splitting on raw newlines first would cut
        # mid-sentence wherever the docstring happened to wrap.
        doc = ' '.join((cls.__doc__ or '').split())
        if doc:
            description = doc.split('. ')[0].rstrip('.')[:220] + '.'

    return {
        'methods': [m for m in methods if m not in ('OPTIONS', 'HEAD')],
        'auth_required': auth_required,
        'description': description,
    }


def _walk(patterns, prefix, out):
    for p in patterns:
        if isinstance(p, URLResolver):
            _walk(p.url_patterns, prefix + str(p.pattern), out)
        elif isinstance(p, URLPattern):
            raw = str(p.pattern)
            # Skip the router's own browsable-API root and the redundant
            # ".<format>"-suffixed duplicate of every router endpoint.
            if p.name == 'api-root' or _FORMAT_SUFFIX_MARKER in raw:
                continue
            info = _inspect_callback(p.callback)
            out.append({
                'path': '/' + _prettify_groups(prefix + _clean_segment(raw)),
                'name': p.name,
                **info,
            })


class ApiDirectoryView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        sections = []
        for module_path, label, url_prefix in _SECTIONS:
            module = importlib.import_module(module_path)
            endpoints = []
            _walk(module.urlpatterns, url_prefix, endpoints)
            endpoints.sort(key=lambda e: e['path'])
            sections.append({'label': label, 'endpoints': endpoints})
        return Response({'sections': sections})
