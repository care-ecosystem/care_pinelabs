from django.utils.encoding import force_str
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from care_pinelabs.settings import plugin_settings
from care_pinelabs.utils.pinelabs import pinelabs_client


class PinelabsWebhookAuthentication(BaseAuthentication):
    """
    Authenticates Pinelabs webhook requests by verifying the
    X-Pinelabs-Signature header against the raw request body using the
    configured webhook secret.

    On success, returns (None, {"source": "pinelabs", "verified": True}).
    We intentionally do not associate a Django user with the request.
    """

    signature_header_name = "HTTP_X_PINELABS_SIGNATURE"

    def authenticate(self, request) -> tuple[None, dict] | None:
        signature = request.META.get(self.signature_header_name)
        if not signature:
            raise AuthenticationFailed("Missing X-Pinelabs-Signature header")

        try:
            # request.body is bytes; SDK expects str
            body_str = force_str(request.body)
            webhook_secret = plugin_settings.PINELABS_WEBHOOK_SECRET
            pinelabs_client.utility.verify_webhook_signature(
                body_str, signature, webhook_secret
            )
        except Exception as e:
            raise AuthenticationFailed("Invalid webhook signature") from e

        return None, {"source": "pinelabs", "verified": True}
