from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import is_hr_or_legacy
from .weather import get_weather_for_location


class BannerInfoView(APIView):
    """Feeds the compact "smart" welcome banner shown on every role's
    dashboard home — weather + region for whichever location this login
    has: an Employee-role profile's own people.Employee.location, or (for
    every other role, which has no Employee record of its own) the
    organization's hq_location. Role/name/timezone are already known
    client-side (auth context + the browser's own clock), so this is the
    only piece that needs a request."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = getattr(request.user, 'profile', None)
        if profile is None:
            return Response({'region': '', 'weather': None, 'can_edit_region': False})

        location = profile.employee.location if profile.employee_id else profile.organization.hq_location
        return Response({
            'region': location,
            'weather': get_weather_for_location(location) if location else None,
            # Only HR ever edits the org-wide fallback; an Employee-role
            # profile's location comes from their own Employee record
            # instead (edited on the Employee Database page, not here).
            'can_edit_region': is_hr_or_legacy(request) and not profile.employee_id,
        })

    def patch(self, request):
        profile = getattr(request.user, 'profile', None)
        if not is_hr_or_legacy(request) or profile is None:
            return Response({'detail': 'Only HR can set the organization location.'}, status=403)

        location = request.data.get('region', '').strip()
        profile.organization.hq_location = location
        profile.organization.save(update_fields=['hq_location'])
        return Response({
            'region': location,
            'weather': get_weather_for_location(location) if location else None,
            'can_edit_region': True,
        })
