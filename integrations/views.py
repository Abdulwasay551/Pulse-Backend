from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsHR, IsOwner, owner_scope_id

from .catalog import public_catalog
from .dispatch import IntegrationError, test_connection
from .models import IntegrationConnection
from .serializers import IntegrationConnectionSerializer


class IntegrationConnectionViewSet(viewsets.ModelViewSet):
    """Connection CRUD is HR/Admin-only, same tier as ai_core's credential
    management — every other role never sees raw config, only whatever
    effect a connected integration has (e.g. a Slack message)."""

    queryset = IntegrationConnection.objects.all()
    serializer_class = IntegrationConnectionSerializer
    permission_classes = [IsAuthenticated, IsOwner | IsHR]

    def get_queryset(self):
        return self.queryset.filter(owner_id=owner_scope_id(self.request))

    def perform_create(self, serializer):
        serializer.save(owner_id=owner_scope_id(self.request))

    @action(detail=True, methods=['post'])
    def test(self, request, pk=None):
        connection = self.get_object()
        try:
            test_connection(connection)
        except IntegrationError as exc:
            return Response({'ok': False, 'detail': str(exc)})
        return Response({'ok': True, 'detail': 'Test notification sent.'})


class IntegrationCatalogView(APIView):
    permission_classes = [IsAuthenticated, IsOwner | IsHR]

    def get(self, request):
        return Response(public_catalog())
