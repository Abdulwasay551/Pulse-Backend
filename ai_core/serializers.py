import ipaddress
from urllib.parse import urlparse

from rest_framework import serializers

from .features import AI_FEATURES
from .models import AIFeatureOverride, AIProviderCredential


def _is_blocked_host(hostname: str) -> bool:
    if not hostname:
        return True
    if hostname.lower() in ('localhost',):
        return True
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        return False  # a real hostname, not a literal IP — can't fully resolve DNS-rebinding here, best-effort only
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved


class AIProviderCredentialSerializer(serializers.ModelSerializer):
    api_key = serializers.CharField(write_only=True, required=False, allow_blank=False)

    class Meta:
        model = AIProviderCredential
        fields = [
            'id', 'provider', 'label', 'base_url', 'model', 'api_key', 'key_last4', 'is_default',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'key_last4', 'is_default', 'created_at', 'updated_at']

    def validate(self, attrs):
        provider = attrs.get('provider', getattr(self.instance, 'provider', None))
        base_url = attrs.get('base_url', getattr(self.instance, 'base_url', ''))
        if provider == 'openai_compatible' and not base_url:
            raise serializers.ValidationError({'base_url': 'Required for a custom OpenAI-compatible provider.'})
        if base_url:
            parsed = urlparse(base_url)
            if parsed.scheme != 'https':
                raise serializers.ValidationError({'base_url': 'Must be an https:// URL.'})
            if _is_blocked_host(parsed.hostname or ''):
                raise serializers.ValidationError({'base_url': 'That host isn\'t reachable from here.'})
        if self.instance is None and not attrs.get('api_key'):
            raise serializers.ValidationError({'api_key': 'Required.'})
        return attrs

    def create(self, validated_data):
        api_key = validated_data.pop('api_key')
        instance = AIProviderCredential(**validated_data)
        instance.set_api_key(api_key)
        instance.save()
        return instance

    def update(self, instance, validated_data):
        api_key = validated_data.pop('api_key', None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if api_key:
            instance.set_api_key(api_key)
        instance.save()
        return instance


class AIFeatureSettingSerializer(serializers.Serializer):
    feature_key = serializers.CharField()
    label = serializers.CharField()
    module = serializers.CharField()
    override_credential = serializers.IntegerField(allow_null=True)
    effective_credential = serializers.SerializerMethodField()
    ai_enabled = serializers.BooleanField()

    def get_effective_credential(self, obj):
        credential = obj.get('credential')
        if not credential:
            return None
        return {'id': credential.id, 'provider': credential.provider, 'model': credential.model}


def feature_settings_payload(owner_id):
    from .registry import resolve_credential_for_feature

    overrides = {o.feature_key: o.credential_id for o in AIFeatureOverride.objects.filter(owner_id=owner_id)}
    rows = []
    for key, meta in AI_FEATURES.items():
        credential = resolve_credential_for_feature(owner_id, key)
        rows.append(
            {
                'feature_key': key,
                'label': meta['label'],
                'module': meta['module'],
                'override_credential': overrides.get(key),
                'credential': credential,
                'ai_enabled': credential is not None,
            }
        )
    return rows
