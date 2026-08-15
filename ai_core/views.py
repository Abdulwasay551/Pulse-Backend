from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsHR, IsOwner, owner_scope_id

from .features import AI_FEATURES
from .models import AIFeatureOverride, AIProviderCredential
from .providers import PROVIDER_CATALOG, AIProviderError, run_completion
from .registry import status_payload
from .serializers import AIFeatureSettingSerializer, AIProviderCredentialSerializer, feature_settings_payload


class AIProviderCredentialViewSet(viewsets.ModelViewSet):
    """Credential CRUD is HR/Admin-only — every other role only ever sees
    the *effect* through AIStatusView, never the raw key management."""

    queryset = AIProviderCredential.objects.all()
    serializer_class = AIProviderCredentialSerializer
    permission_classes = [IsAuthenticated, IsOwner | IsHR]

    def get_queryset(self):
        return self.queryset.filter(owner_id=owner_scope_id(self.request))

    def perform_create(self, serializer):
        serializer.save(owner_id=owner_scope_id(self.request))

    @action(detail=True, methods=['post'], url_path='set-default')
    def set_default(self, request, pk=None):
        credential = self.get_object()
        with transaction.atomic():
            AIProviderCredential.objects.filter(owner_id=owner_scope_id(request), is_default=True).exclude(
                pk=credential.pk
            ).update(is_default=False)
            credential.is_default = True
            credential.save(update_fields=['is_default'])
        return Response(AIProviderCredentialSerializer(credential).data)

    @action(detail=True, methods=['post'])
    def test(self, request, pk=None):
        credential = self.get_object()
        try:
            run_completion(
                credential,
                system='Reply with exactly one word: ok',
                user_prompt='ping',
                json_mode=False,
                max_tokens=5,
            )
        except AIProviderError as exc:
            return Response({'ok': False, 'detail': str(exc)})
        return Response({'ok': True, 'detail': 'Connected.'})


class AIProviderCatalogView(APIView):
    permission_classes = [IsAuthenticated, IsOwner | IsHR]

    def get(self, request):
        return Response(PROVIDER_CATALOG)


class AIFeatureSettingsView(APIView):
    permission_classes = [IsAuthenticated, IsOwner | IsHR]

    def get(self, request):
        rows = feature_settings_payload(owner_scope_id(request))
        return Response(AIFeatureSettingSerializer(rows, many=True).data)


class AIFeatureOverrideView(APIView):
    permission_classes = [IsAuthenticated, IsOwner | IsHR]

    def put(self, request, feature_key):
        if feature_key not in AI_FEATURES:
            return Response({'detail': 'Unknown feature.'}, status=status.HTTP_404_NOT_FOUND)
        uid = owner_scope_id(request)
        credential_id = request.data.get('credential')
        if credential_id is None:
            AIFeatureOverride.objects.filter(owner_id=uid, feature_key=feature_key).delete()
        else:
            credential = AIProviderCredential.objects.filter(owner_id=uid, pk=credential_id).first()
            if not credential:
                return Response({'detail': 'Credential not found.'}, status=status.HTTP_400_BAD_REQUEST)
            AIFeatureOverride.objects.update_or_create(
                owner_id=uid, feature_key=feature_key, defaults={'credential': credential}
            )
        rows = feature_settings_payload(uid)
        row = next(r for r in rows if r['feature_key'] == feature_key)
        return Response(AIFeatureSettingSerializer(row).data)


class AIStatusView(APIView):
    """The lightweight call any AI-touched page/section needs — covers
    every registered feature in one round trip, so adding a new AI feature
    later needs zero new frontend endpoints, just a new key in
    ai_core.features.AI_FEATURES."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(status_payload(owner_scope_id(request)))
