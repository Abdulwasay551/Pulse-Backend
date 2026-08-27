from django.conf import settings
from django.shortcuts import render
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .api_auth import generate_token
from .models import ApiToken, Announcement
from .permissions import IsOwner
from .serializers import ApiTokenSerializer, AnnouncementSerializer


@api_view(['GET'])
def health(request):
    return Response({'status': 'ok'})


def landing(request):
    return render(request, 'core/landing.html', {'frontend_url': settings.FRONTEND_URL})


class AnnouncementViewSet(viewsets.ModelViewSet):
    queryset = Announcement.objects.all()
    serializer_class = AnnouncementSerializer
    permission_classes = [IsAuthenticated, IsOwner]

    def get_queryset(self):
        return self.queryset.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class ApiTokenViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """Self-service personal API tokens — deliberately no IsOwner/IsHR
    gating beyond IsAuthenticated: every user manages only their own
    tokens (scoped by request.user, not by owner_scope_id's org-wide
    tenant), and a token issued here only ever carries that same user's
    existing permissions (see core.api_auth.ApiTokenAuthentication) — an
    Employee's token can't do anything an Employee couldn't already do
    logged in normally."""

    queryset = ApiToken.objects.all()
    serializer_class = ApiTokenSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        token, raw = generate_token(request.user, label=request.data.get('label', ''))
        data = ApiTokenSerializer(token).data
        # The only time the plaintext value is ever available — the
        # frontend must show it once and never fetch it again.
        data['token'] = raw
        return Response(data, status=201)

    @action(detail=True, methods=['post'])
    def revoke(self, request, pk=None):
        token = self.get_object()
        if not token.revoked_at:
            token.revoked_at = timezone.now()
            token.save(update_fields=['revoked_at'])
        return Response(ApiTokenSerializer(token).data)
