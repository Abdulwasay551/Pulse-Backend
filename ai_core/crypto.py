from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


@lru_cache
def _fernet() -> Fernet:
    key = settings.AI_CREDENTIAL_ENCRYPTION_KEY
    if not key:
        raise ImproperlyConfigured('AI_CREDENTIAL_ENCRYPTION_KEY is not set.')
    return Fernet(key)


def encrypt_secret(plaintext: str) -> bytes:
    return _fernet().encrypt(plaintext.encode())


def decrypt_secret(ciphertext: bytes) -> str:
    try:
        return _fernet().decrypt(bytes(ciphertext)).decode()
    except InvalidToken as exc:
        raise ImproperlyConfigured('Stored AI credential could not be decrypted.') from exc
