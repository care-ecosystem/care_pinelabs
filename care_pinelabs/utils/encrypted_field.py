import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.db import models

from care_pinelabs.settings import plugin_settings


def _get_fernet() -> Fernet:
    key = base64.urlsafe_b64encode(
        hashlib.sha256(plugin_settings.PINELABS_SECRET_KEY.encode()).digest()
    )
    return Fernet(key)


class EncryptedCharField(models.TextField):
    """
    Transparently encrypts the value at rest using Fernet (symmetric,
    reversible) — unlike Django's password hashing, the plaintext must be
    recoverable to send back to the third-party gateway.
    """

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None:
            return value
        return _get_fernet().encrypt(value.encode()).decode()

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        try:
            return _get_fernet().decrypt(value.encode()).decode()
        except InvalidToken:
            return value
