"""Dropbox Sign — BYOK via a plain API key (Basic Auth, key as username,
blank password, per Dropbox Sign's own docs). OfferLetter.body is plain
text, not a PDF, so send_for_signature renders it to a simple one-page PDF
with reportlab (already a dependency — see people/certificates.py) before
uploading; Dropbox Sign's signature_request/send endpoint only accepts
real files, not raw text."""

import hashlib
import hmac
import io

import requests
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from .helpers import get_connection

_API_BASE = 'https://api.hellosign.com/v3'


class DropboxSignError(Exception):
    pass


def _auth(config):
    return (config['api_key'], '')


def _render_offer_letter_pdf(offer_letter) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=1 * inch, bottomMargin=1 * inch)
    styles = getSampleStyleSheet()
    story = [
        Paragraph(f'Offer of Employment — {offer_letter.job_title}', styles['Title']),
        Spacer(1, 0.3 * inch),
    ]
    for para in offer_letter.body.split('\n\n'):
        story.append(Paragraph(para.replace('\n', '<br/>'), styles['Normal']))
        story.append(Spacer(1, 0.15 * inch))
    doc.build(story)
    return buffer.getvalue()


def test_credentials(config):
    """Used by the settings page's "Test" button — a cheap authenticated
    GET, no signature request sent."""
    resp = requests.get(f'{_API_BASE}/account', auth=_auth(config), timeout=8)
    if not resp.ok:
        raise DropboxSignError(f'Dropbox Sign rejected this API key: {resp.text[:200]}')


def send_for_signature(owner_id, offer_letter):
    """Emails the candidate a real Dropbox Sign signature request for this
    offer letter. Returns the signature_request_id to store on the
    OfferLetter — the webhook receiver matches on it to flip status to
    'Signed' once Dropbox Sign confirms everyone's signed."""
    connection = get_connection(owner_id, 'dropbox_sign')
    if not connection:
        raise DropboxSignError('Dropbox Sign is not connected. Connect it under Settings -> Integrations first.')
    if not offer_letter.candidate.email:
        raise DropboxSignError("This candidate has no email on file to send the signature request to.")
    config = connection.get_config()

    pdf_bytes = _render_offer_letter_pdf(offer_letter)
    resp = requests.post(
        f'{_API_BASE}/signature_request/send',
        auth=_auth(config),
        data={
            'title': f'Offer — {offer_letter.candidate.name}',
            'subject': f'Your offer letter for {offer_letter.job_title}',
            'message': 'Please review and sign your offer letter at your earliest convenience.',
            'signers[0][email_address]': offer_letter.candidate.email,
            'signers[0][name]': offer_letter.candidate.name,
        },
        files={'file[0]': ('offer_letter.pdf', pdf_bytes, 'application/pdf')},
        timeout=15,
    )
    if not resp.ok:
        raise DropboxSignError(f'Dropbox Sign could not send the request: {resp.text[:200]}')
    return resp.json()['signature_request']['signature_request_id']


def verify_webhook_signature(config, payload_body: bytes, signature_header: str) -> bool:
    secret = config.get('webhook_secret')
    if not secret:
        return True
    expected = hmac.new(secret.encode(), payload_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header or '')
