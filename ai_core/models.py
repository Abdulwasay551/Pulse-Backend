from django.conf import settings
from django.db import models

from .crypto import decrypt_secret, encrypt_secret
from .features import AI_FEATURE_CHOICES


class AIProviderCredential(models.Model):
    """One row per AI provider an org's HR/Admin has connected. `model` is
    deliberately free text, not a choices field — provider model names ship
    monthly and hard-coding them would need a backend deploy every time
    OpenAI/Anthropic/Google ship something new; the settings UI still offers
    a suggestion list from `ai_core.providers.PROVIDER_CATALOG`."""

    PROVIDER_CHOICES = [
        ('openai', 'OpenAI'),
        ('anthropic', 'Anthropic (Claude)'),
        ('google', 'Google (Gemini)'),
        ('openrouter', 'OpenRouter'),
        ('deepseek', 'DeepSeek'),
        ('openai_compatible', 'Other (OpenAI-compatible)'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ai_provider_credentials')
    provider = models.CharField(max_length=30, choices=PROVIDER_CHOICES)
    label = models.CharField(max_length=100, blank=True)
    # Only used/required for provider='openai_compatible' — any other
    # OpenAI-chat-completions-shaped endpoint (Groq, Mistral, a local
    # Ollama/vLLM server, etc.), which is the entire extensibility story for
    # "any other famous AI" without needing new code per provider.
    base_url = models.URLField(blank=True)
    model = models.CharField(max_length=100)
    encrypted_api_key = models.BinaryField()
    key_last4 = models.CharField(max_length=4, blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['owner'], condition=models.Q(is_default=True), name='one_default_ai_credential_per_owner'
            ),
        ]

    def __str__(self):
        return f'{self.get_provider_display()} — {self.label or self.model}'

    def set_api_key(self, plaintext: str):
        self.encrypted_api_key = encrypt_secret(plaintext)
        self.key_last4 = plaintext[-4:] if len(plaintext) >= 4 else plaintext

    def get_api_key(self) -> str:
        return decrypt_secret(self.encrypted_api_key)


class AIFeatureOverride(models.Model):
    """Presence of a row = this feature is pinned to a specific credential,
    overriding the org's default. Absence = the feature falls through to
    whichever AIProviderCredential has is_default=True (or is unconfigured,
    if there is no default either)."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ai_feature_overrides')
    feature_key = models.CharField(max_length=50, choices=AI_FEATURE_CHOICES)
    credential = models.ForeignKey(
        AIProviderCredential, on_delete=models.SET_NULL, null=True, related_name='feature_overrides'
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('owner', 'feature_key')]

    def __str__(self):
        return f'{self.feature_key} -> {self.credential}'
