def get_connection(owner_id, integration_key):
    """The enabled connection (if any) an org has for one integration —
    every action-integration provider (Zoom/Checkr/Dropbox Sign) starts
    here rather than querying IntegrationConnection directly."""
    from .models import IntegrationConnection

    return IntegrationConnection.objects.filter(
        owner_id=owner_id, integration_key=integration_key, is_enabled=True
    ).first()
