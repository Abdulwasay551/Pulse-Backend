"""Public (no auth) receivers for the two integrations that report status
back asynchronously — Checkr (background check results) and Dropbox Sign
(signature completion). Each org's webhook URL is scoped by its own
connection id (.../webhooks/checkr/<connection_id>/) since these third
parties have no notion of our own auth tokens; the connection's own
webhook_secret (optional, set during setup) is what actually verifies a
request is genuine, not the URL's obscurity alone."""

import json
import logging

from django.http import HttpResponse
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .checkr_provider import map_report_status, verify_webhook_signature as verify_checkr_signature
from .dropbox_sign_provider import verify_webhook_signature as verify_dropbox_sign_signature
from .models import IntegrationConnection

logger = logging.getLogger(__name__)


class CheckrWebhookView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, connection_id):
        connection = IntegrationConnection.objects.filter(pk=connection_id, integration_key='checkr').first()
        if not connection:
            return Response(status=404)
        config = connection.get_config()
        if not verify_checkr_signature(config, request.body, request.headers.get('X-Checkr-Signature', '')):
            return Response(status=403)

        payload = request.data
        obj = (payload.get('data') or {}).get('object') or {}
        report_id = obj.get('id')
        checkr_status = obj.get('status')
        if not report_id or not checkr_status:
            return Response({'detail': 'ignored'}, status=200)

        from recruit.models import BackgroundCheck

        check = BackgroundCheck.objects.filter(
            owner_id=connection.owner_id, checkr_report_id=report_id
        ).first()
        if check:
            check.status = map_report_status(checkr_status)
            if check.status in ('Cleared', 'Flagged') and not check.completed_at:
                check.completed_at = timezone.now()
            check.save(update_fields=['status', 'completed_at', 'updated_at'])
        return Response({'detail': 'ok'}, status=200)


class DropboxSignWebhookView(APIView):
    """Dropbox Sign posts form-encoded data with a `json` field, and
    requires the exact literal string response below for every event
    (including its own callback-verification test) or it deactivates the
    webhook — see their "Event Callback Response" docs."""

    permission_classes = [AllowAny]

    def post(self, request, connection_id):
        connection = IntegrationConnection.objects.filter(pk=connection_id, integration_key='dropbox_sign').first()
        if not connection:
            return Response(status=404)
        config = connection.get_config()

        raw = request.POST.get('json', '{}')
        signature = request.POST.get('signature', '')
        if not verify_dropbox_sign_signature(config, raw.encode(), signature):
            return HttpResponse('Hello API Event Received', status=403, content_type='text/plain')

        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            payload = {}

        event_type = ((payload.get('event') or {}).get('event_type')) or ''
        sig_request = payload.get('signature_request') or {}
        request_id = sig_request.get('signature_request_id')

        if event_type == 'signature_request_all_signed' and request_id:
            from recruit.models import OfferLetter

            offer = OfferLetter.objects.filter(
                owner_id=connection.owner_id, dropbox_sign_request_id=request_id
            ).first()
            if offer and offer.status != 'Signed':
                offer.status = 'Signed'
                offer.signed_at = timezone.now()
                offer.save(update_fields=['status', 'signed_at', 'updated_at'])

        return HttpResponse('Hello API Event Received', status=200, content_type='text/plain')
