"""The single registry every integration is defined in — adding a new one
later means adding an entry here (plus a `dispatch.py` sender if it needs
one) rather than a new model/serializer/viewset per app. Mirrors the same
"data over code" shape ai_core.providers/features already use for AI
providers, generalized to any third-party connection.

Each entry:
  label / description / category — shown on the settings page.
  setup_instructions — plain text, line-broken; walks the user through
    getting the credential from the third party's own site. This is the
    whole point of the feature per the product ask: never assume the user
    knows where to find an API key.
  fields — the form the settings page renders and the exact keys stored
    (encrypted, as one JSON blob) in IntegrationConnection.config.
  notify_tones — which ActivityLog tones this integration fires a
    notification for (see core.activity.log_activity's dispatch hook).
    Deliberately excludes 'neutral' (routine, high-volume activity) by
    default so connecting one of these doesn't flood a channel/phone with
    every minor CRUD action — only real milestones/flags.
"""

NOTIFY_TONES_DEFAULT = {'primary', 'amber', 'maroon'}
NOTIFY_TONES_CRITICAL_ONLY = {'maroon'}

INTEGRATIONS = {
    'slack': {
        'label': 'Slack',
        'category': 'Notifications',
        'description': 'Post key events (new hires, payroll runs, approvals, flags) to a Slack channel.',
        'setup_instructions': (
            'Create a Slack Incoming Webhook:\n'
            '1. Go to api.slack.com/apps and click "Create New App" -> "From scratch".\n'
            '2. Name it (e.g. "Pulse Notifications") and pick your workspace.\n'
            '3. Open "Incoming Webhooks" in the left sidebar and toggle it on.\n'
            '4. Click "Add New Webhook to Workspace", choose the channel to post to, and allow it.\n'
            '5. Copy the Webhook URL Slack gives you (starts with https://hooks.slack.com/services/…) '
            'and paste it below.'
        ),
        'fields': [
            {
                'name': 'webhook_url', 'label': 'Webhook URL', 'type': 'url', 'secret': True, 'required': True,
                'placeholder': 'https://hooks.slack.com/services/…',
            },
        ],
        'notify_tones': NOTIFY_TONES_DEFAULT,
    },
    'teams': {
        'label': 'Microsoft Teams',
        'category': 'Notifications',
        'description': 'Post key events to a Microsoft Teams channel.',
        'setup_instructions': (
            'Create a Teams Incoming Webhook:\n'
            '1. In Teams, open the channel you want notifications in, click "…" -> "Workflows".\n'
            '2. Search for and select "Post to a channel when a webhook request is received".\n'
            '3. Follow the prompts to create it, choosing this channel as the destination.\n'
            '4. Copy the webhook URL it gives you at the end and paste it below.'
        ),
        'fields': [
            {
                'name': 'webhook_url', 'label': 'Webhook URL', 'type': 'url', 'secret': True, 'required': True,
                'placeholder': 'https://….webhook.office.com/webhookb2/…',
            },
        ],
        'notify_tones': NOTIFY_TONES_DEFAULT,
    },
    'webhook': {
        'label': 'Custom Webhook',
        'category': 'Automation',
        'description': (
            'Send a JSON POST for every notable event to any URL you control — the generic bridge into '
            'Zapier, Make.com, n8n, or your own service, without waiting on a dedicated integration.'
        ),
        'setup_instructions': (
            'Point this at any endpoint that accepts a JSON POST:\n'
            '1. In Zapier/Make.com/n8n, create a new automation and choose "Webhooks" as the trigger.\n'
            '2. Copy the custom webhook URL it gives you.\n'
            '3. Paste it below. Every notable event sends {"event": "...", "message": "...", "tone": "..."}.'
        ),
        'fields': [
            {
                'name': 'webhook_url', 'label': 'Webhook URL', 'type': 'url', 'secret': True, 'required': True,
                'placeholder': 'https://hooks.zapier.com/hooks/catch/…',
            },
        ],
        'notify_tones': NOTIFY_TONES_DEFAULT,
    },
    'twilio': {
        'label': 'Twilio (SMS)',
        'category': 'Notifications',
        'description': 'Text a phone number for critical, time-sensitive events only (e.g. a flagged payroll discrepancy).',
        'setup_instructions': (
            'Get your Twilio credentials:\n'
            '1. Sign up / log in at twilio.com/console.\n'
            '2. On the console dashboard, copy your Account SID and Auth Token.\n'
            '3. Under Phone Numbers -> Manage -> Active Numbers, copy (or buy) a Twilio number to send from.\n'
            '4. Fill in all three fields below, plus the phone number that should receive alerts.'
        ),
        'fields': [
            {'name': 'account_sid', 'label': 'Account SID', 'type': 'text', 'secret': True, 'required': True, 'placeholder': 'ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'},
            {'name': 'auth_token', 'label': 'Auth Token', 'type': 'password', 'secret': True, 'required': True},
            {'name': 'from_number', 'label': 'Twilio phone number', 'type': 'text', 'secret': False, 'required': True, 'placeholder': '+15551234567'},
            {'name': 'to_number', 'label': 'Alert phone number', 'type': 'text', 'secret': False, 'required': True, 'placeholder': '+15557654321'},
        ],
        # SMS is per-message priced and easy to make painful — critical-only.
        'notify_tones': NOTIFY_TONES_CRITICAL_ONLY,
    },
}


def get_integration(key):
    return INTEGRATIONS.get(key)


def public_catalog():
    """Same shape as INTEGRATIONS but with secret-marked field values never
    present in the first place (there's nothing to strip — the catalog
    itself holds no credentials, only field *definitions*), returned as
    plain dicts for the settings page to render forms + instructions from."""
    return {
        key: {
            'label': meta['label'],
            'category': meta['category'],
            'description': meta['description'],
            'setup_instructions': meta['setup_instructions'],
            'fields': meta['fields'],
        }
        for key, meta in INTEGRATIONS.items()
    }
