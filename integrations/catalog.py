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
    'discord': {
        'label': 'Discord',
        'category': 'Notifications',
        'description': 'Post key events (new hires, payroll runs, approvals, flags) to a Discord channel.',
        'setup_instructions': (
            'Create a Discord webhook:\n'
            '1. In Discord, open the channel you want notifications in and click the gear icon (Edit Channel).\n'
            '2. Go to Integrations -> Webhooks -> New Webhook.\n'
            '3. Name it (e.g. "Pulse Notifications") and click Copy Webhook URL.\n'
            '4. Paste that URL below.'
        ),
        'fields': [
            {
                'name': 'webhook_url', 'label': 'Webhook URL', 'type': 'url', 'secret': True, 'required': True,
                'placeholder': 'https://discord.com/api/webhooks/…',
            },
        ],
        'notify_tones': NOTIFY_TONES_DEFAULT,
    },
    'telegram': {
        'label': 'Telegram',
        'category': 'Notifications',
        'description': 'Message a Telegram chat or channel for key events.',
        'setup_instructions': (
            'Create a Telegram bot and find your chat ID:\n'
            '1. In Telegram, message @BotFather, send /newbot, and follow the prompts — it gives you a Bot Token.\n'
            '2. Add your new bot to the chat/channel you want notifications in (or just message it directly).\n'
            '3. Send it any message, then visit '
            'https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates in a browser to find the "chat":{"id": ...} '
            'value — that\'s your Chat ID.\n'
            '4. Paste both below.'
        ),
        'fields': [
            {'name': 'bot_token', 'label': 'Bot Token', 'type': 'password', 'secret': True, 'required': True, 'placeholder': '123456789:AAExampleTokenValue'},
            {'name': 'chat_id', 'label': 'Chat ID', 'type': 'text', 'secret': False, 'required': True, 'placeholder': '-1001234567890'},
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
    'smtp': {
        'label': 'Email (SMTP)',
        'category': 'Email',
        'description': (
            'Send this org\'s password-reset and invite emails through your own mail provider instead of '
            'Pulse\'s shared default — every email then comes from your own address and domain.'
        ),
        'setup_instructions': (
            'Use any SMTP provider — SendGrid, Mailgun, Postmark, Amazon SES, Google Workspace, or your own '
            'mail server:\n'
            '1. In your provider\'s dashboard, create an SMTP-sending API key or app password (e.g. SendGrid: '
            'Settings -> API Keys; Google Workspace: an App Password on the sending account).\n'
            '2. Copy the SMTP host and port from the same page (e.g. SendGrid is smtp.sendgrid.net, port 587).\n'
            '3. Fill in the fields below — the username is often literally "apikey" for API-key-based '
            'providers like SendGrid, not an email address; check your provider\'s docs if unsure.'
        ),
        'fields': [
            {'name': 'host', 'label': 'SMTP Host', 'type': 'text', 'secret': False, 'required': True, 'placeholder': 'smtp.sendgrid.net'},
            {'name': 'port', 'label': 'Port', 'type': 'text', 'secret': False, 'required': True, 'placeholder': '587'},
            {'name': 'username', 'label': 'Username', 'type': 'text', 'secret': True, 'required': True},
            {'name': 'password', 'label': 'Password / API Key', 'type': 'password', 'secret': True, 'required': True},
            {'name': 'from_email', 'label': 'From address', 'type': 'text', 'secret': False, 'required': True, 'placeholder': 'no-reply@yourcompany.com'},
        ],
        'notify_tones': set(),
    },
    'zoom': {
        'label': 'Zoom',
        'category': 'Recruiting',
        'description': 'Create a real Zoom meeting link for a candidate interview with one click.',
        'setup_instructions': (
            'Create a Zoom Server-to-Server OAuth app (no browser sign-in flow needed):\n'
            '1. Go to marketplace.zoom.us/develop/create and choose "Server-to-Server OAuth".\n'
            '2. Name it (e.g. "Pulse Interviews") and finish activating it.\n'
            '3. Under Scopes, add meeting:write:meeting (and meeting:write:meeting:admin if you want to '
            'create meetings on behalf of other users on the account).\n'
            '4. Open the app\'s "App Credentials" tab and copy the Account ID, Client ID, and Client Secret below.'
        ),
        'fields': [
            {'name': 'account_id', 'label': 'Account ID', 'type': 'text', 'secret': True, 'required': True},
            {'name': 'client_id', 'label': 'Client ID', 'type': 'text', 'secret': True, 'required': True},
            {'name': 'client_secret', 'label': 'Client Secret', 'type': 'password', 'secret': True, 'required': True},
        ],
        # Action-only integration (invoked by "Create Zoom meeting"), not a
        # passive log_activity subscriber.
        'notify_tones': set(),
    },
    'checkr': {
        'label': 'Checkr',
        'category': 'Recruiting',
        'description': 'Run real background checks on candidates — status updates flow back automatically.',
        'setup_instructions': (
            '1. Sign up / log in at dashboard.checkr.com.\n'
            '2. Go to Account -> API Keys and copy your API key (use a Test key while trying this out).\n'
            '3. Go to Account -> Webhooks, add a webhook pointing at the URL shown after you connect below, '
            'and copy the Webhook Signing Secret it gives you.\n'
            '4. Paste both below. Sending a background check will email the candidate and the report status '
            'will update on its own as Checkr processes it.'
        ),
        'fields': [
            {'name': 'api_key', 'label': 'API Key', 'type': 'password', 'secret': True, 'required': True},
            {'name': 'webhook_secret', 'label': 'Webhook Signing Secret', 'type': 'password', 'secret': True, 'required': False},
        ],
        'notify_tones': set(),
    },
    'dropbox_sign': {
        'label': 'Dropbox Sign',
        'category': 'Recruiting',
        'description': 'Send offer letters out for real, legally-binding e-signature.',
        'setup_instructions': (
            '1. Sign up / log in at app.hellosign.com (Dropbox Sign).\n'
            '2. Go to Settings -> API and copy your API key.\n'
            '3. On the same page, set the Event Callback URL to the URL shown after you connect below, and '
            'copy the API Event Callback / Webhook secret it gives you.\n'
            '4. Paste both below. Sending an offer letter will email the candidate a real signature request, '
            'and it\'ll be marked Signed here automatically once they sign.'
        ),
        'fields': [
            {'name': 'api_key', 'label': 'API Key', 'type': 'password', 'secret': True, 'required': True},
            {'name': 'webhook_secret', 'label': 'Event Callback Secret', 'type': 'password', 'secret': True, 'required': False},
        ],
        'notify_tones': set(),
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
