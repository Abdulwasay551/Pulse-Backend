from .features import AI_FEATURES
from .models import AIFeatureOverride, AIProviderCredential


def resolve_credential_for_feature(owner_id, feature_key):
    override = (
        AIFeatureOverride.objects.filter(owner_id=owner_id, feature_key=feature_key)
        .select_related('credential')
        .first()
    )
    if override and override.credential_id:
        return override.credential
    return AIProviderCredential.objects.filter(owner_id=owner_id, is_default=True).first()


def is_feature_enabled(owner_id, feature_key) -> bool:
    return resolve_credential_for_feature(owner_id, feature_key) is not None


def status_payload(owner_id):
    return {
        'has_default': AIProviderCredential.objects.filter(owner_id=owner_id, is_default=True).exists(),
        'features': {key: is_feature_enabled(owner_id, key) for key in AI_FEATURES},
    }
