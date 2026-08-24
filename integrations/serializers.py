from rest_framework import serializers

from .catalog import INTEGRATIONS
from .models import IntegrationConnection


_WEBHOOK_INTEGRATIONS = {'checkr': 'checkr-webhook', 'dropbox_sign': 'dropbox-sign-webhook'}


class IntegrationConnectionSerializer(serializers.ModelSerializer):
    config = serializers.DictField(write_only=True)
    masked_config = serializers.SerializerMethodField()
    label_display = serializers.CharField(source='get_integration_key_display', read_only=True)
    webhook_receiver_url = serializers.SerializerMethodField()

    class Meta:
        model = IntegrationConnection
        fields = [
            'id', 'integration_key', 'label_display', 'label', 'config', 'masked_config',
            'is_enabled', 'webhook_receiver_url', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_masked_config(self, obj):
        return obj.masked_config()

    def get_webhook_receiver_url(self, obj):
        """Only integrations that report status back asynchronously (Checkr,
        Dropbox Sign) need the org to paste a URL back into that third
        party's own dashboard — everything else is one-directional."""
        url_name = _WEBHOOK_INTEGRATIONS.get(obj.integration_key)
        if not url_name:
            return None
        from django.urls import reverse

        request = self.context.get('request')
        path = reverse(url_name, kwargs={'connection_id': obj.id})
        return request.build_absolute_uri(path) if request else path

    def validate(self, attrs):
        integration_key = attrs.get('integration_key') or getattr(self.instance, 'integration_key', None)
        meta = INTEGRATIONS.get(integration_key)
        if not meta:
            raise serializers.ValidationError({'integration_key': ['Unknown integration.']})
        config = attrs.get('config')
        if config is not None:
            missing = [
                f['label'] for f in meta['fields']
                if f.get('required') and not str(config.get(f['name'], '')).strip()
            ]
            if missing:
                raise serializers.ValidationError({'config': [f'Missing required field(s): {", ".join(missing)}.']})
            allowed_names = {f['name'] for f in meta['fields']}
            attrs['config'] = {k: v for k, v in config.items() if k in allowed_names}
        return attrs

    def create(self, validated_data):
        config = validated_data.pop('config')
        instance = IntegrationConnection(**validated_data)
        instance.set_config(config)
        instance.save()
        return instance

    def update(self, instance, validated_data):
        config = validated_data.pop('config', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if config is not None:
            # A masked secret field left untouched by the settings form is
            # resubmitted as-is (e.g. "••••1234") — don't overwrite the real
            # stored value with that mask. Only fields whose value actually
            # changed (not just the masked placeholder) get updated.
            existing = instance.get_config()
            meta = INTEGRATIONS[instance.integration_key]
            secret_names = {f['name'] for f in meta['fields'] if f.get('secret')}
            merged = dict(existing)
            for key, value in config.items():
                if key in secret_names and isinstance(value, str) and value.startswith('••••'):
                    continue
                merged[key] = value
            instance.set_config(merged)
        instance.save()
        return instance
