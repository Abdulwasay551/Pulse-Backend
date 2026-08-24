import json

from django.conf import settings
from django.db import models

from ai_core.crypto import decrypt_secret, encrypt_secret

from .catalog import INTEGRATIONS


class IntegrationConnection(models.Model):
    """One row per third-party app an org has connected. `config` holds
    every field the integration's catalog entry defines (secret and
    non-secret alike) as one Fernet-encrypted JSON blob — simpler than a
    typed column per field, and the whole point of the catalog-driven
    design is that a new integration's field shape never needs a schema
    migration. Reuses ai_core's encryption key/helpers rather than
    standing up a second one for the same "encrypt third-party
    credentials at rest" job."""

    INTEGRATION_CHOICES = [(key, meta['label']) for key, meta in INTEGRATIONS.items()]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='integration_connections')
    integration_key = models.CharField(max_length=30, choices=INTEGRATION_CHOICES)
    label = models.CharField(max_length=100, blank=True)
    encrypted_config = models.BinaryField()
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['owner', 'integration_key'], name='one_connection_per_owner_per_integration'),
        ]

    def __str__(self):
        return f'{self.get_integration_key_display()} — {self.label or self.owner_id}'

    def set_config(self, config: dict):
        self.encrypted_config = encrypt_secret(json.dumps(config))

    def get_config(self) -> dict:
        return json.loads(decrypt_secret(self.encrypted_config))

    def masked_config(self) -> dict:
        """Non-secret fields as-is; secret fields collapsed to a last-4
        hint — what the settings page is allowed to see back after saving,
        same "never re-display the real value" rule ai_core's key_last4
        already follows."""
        meta = INTEGRATIONS.get(self.integration_key, {})
        secret_names = {f['name'] for f in meta.get('fields', []) if f.get('secret')}
        config = self.get_config()
        masked = {}
        for name, value in config.items():
            if name in secret_names and isinstance(value, str):
                masked[name] = f'••••{value[-4:]}' if len(value) >= 4 else '••••'
            else:
                masked[name] = value
        return masked
