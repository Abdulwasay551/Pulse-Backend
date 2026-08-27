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
    # Temporarily disabled — remove this comment block to bring Teams back.
    # 'teams': {
    #     'label': 'Microsoft Teams',
    #     'category': 'Notifications',
    #     'description': 'Post key events to a Microsoft Teams channel.',
    #     'setup_instructions': (
    #         'Create a Teams Incoming Webhook:\n'
    #         '1. In Teams, open the channel you want notifications in, click "…" -> "Workflows".\n'
    #         '2. Search for and select "Post to a channel when a webhook request is received".\n'
    #         '3. Follow the prompts to create it, choosing this channel as the destination.\n'
    #         '4. Copy the webhook URL it gives you at the end and paste it below.'
    #     ),
    #     'fields': [
    #         {
    #             'name': 'webhook_url', 'label': 'Webhook URL', 'type': 'url', 'secret': True, 'required': True,
    #             'placeholder': 'https://….webhook.office.com/webhookb2/…',
    #         },
    #     ],
    #     'notify_tones': NOTIFY_TONES_DEFAULT,
    # },
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
    'zapier': {
        'label': 'Zapier',
        'category': 'Automation',
        'description': (
            'Trigger a Zap for every notable event — new hires, payroll runs, approvals, flags — '
            'and fan it out to the 7,000+ apps Zapier connects to.'
        ),
        'setup_instructions': (
            'Uses Zapier\'s own "Webhooks by Zapier" trigger — no Zapier developer account needed:\n'
            '1. In Zapier, create a new Zap and choose "Webhooks by Zapier" as the trigger app.\n'
            '2. Pick the "Catch Hook" event, then copy the custom webhook URL it gives you.\n'
            '3. Paste it below. Every notable event sends {"event": "...", "message": "...", "tone": "..."} '
            'as the Zap\'s trigger payload — map those fields to whatever action you build downstream.'
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
    'wise': {
        'label': 'Wise',
        'category': 'Payroll',
        'description': 'Get real international transfer quotes and verify recipient bank details for cross-border payroll.',
        'setup_instructions': (
            '1. Sign up / log in at wise.com (a Wise Business account is recommended for payroll use).\n'
            '2. Go to Settings -> API tokens and click "Create new token" (choose a Full access token if you '
            'want to verify recipient accounts, or Read-only if you only want quotes).\n'
            '3. Paste it below. Nothing here moves money — quotes and verification are both read-only checks '
            'against Wise\'s live rates and account-validation rules.'
        ),
        'fields': [
            {'name': 'api_token', 'label': 'API Token', 'type': 'password', 'secret': True, 'required': True},
        ],
        'notify_tones': set(),
    },
    'deel': {
        'label': 'Deel',
        'category': 'Payroll',
        'description': 'Connect your Deel account to confirm live access to your EOR/contractor workforce data.',
        'setup_instructions': (
            '1. Log in to app.deel.com as an account admin.\n'
            '2. Go to Developer Center (or Settings -> API) and generate a new API key.\n'
            '3. Paste it below.'
        ),
        'fields': [
            {'name': 'api_token', 'label': 'API Key', 'type': 'password', 'secret': True, 'required': True},
        ],
        'notify_tones': set(),
    },
    'remote': {
        'label': 'Remote',
        'category': 'Payroll',
        'description': 'Connect your Remote account to confirm live access to your EOR workforce data.',
        'setup_instructions': (
            '1. Log in to app.remote.com as an account admin.\n'
            '2. Go to Integrations & API -> API keys and create a new key.\n'
            '3. Paste it below.'
        ),
        'fields': [
            {'name': 'api_token', 'label': 'API Key', 'type': 'password', 'secret': True, 'required': True},
        ],
        'notify_tones': set(),
    },
    'hackerrank': {
        'label': 'HackerRank',
        'category': 'Recruiting',
        'description': 'Send a real technical assessment to a candidate and pull their score back.',
        'setup_instructions': (
            '1. Sign up / log in at hackerrank.com/work (a HackerRank for Work account).\n'
            '2. Create at least one test under Tests -> Create Test — copy its Test ID from the test\'s '
            'own settings/URL (you\'ll enter it when sending a test to a candidate, so different roles '
            'can use different tests).\n'
            '3. Go to Account Settings -> API and copy your API token.\n'
            '4. Paste it below.'
        ),
        'fields': [
            {'name': 'api_token', 'label': 'API Token', 'type': 'password', 'secret': True, 'required': True},
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
    'surveymonkey': {
        'label': 'SurveyMonkey',
        'category': 'People',
        'description': 'Pull in your existing SurveyMonkey surveys and response counts alongside Pulse\'s own Surveys page.',
        'setup_instructions': (
            'Create a SurveyMonkey Private App (self-serve, no partner approval needed):\n'
            '1. Log in at surveymonkey.com and go to Account -> API -> Add a New App.\n'
            '2. Choose "Private App" (for connecting your own account to an internal tool like this one).\n'
            '3. Under Scopes, enable at least "View Surveys" (read-only is all this needs).\n'
            '4. Copy the Access Token it generates and paste it below.'
        ),
        'fields': [
            {'name': 'api_token', 'label': 'Access Token', 'type': 'password', 'secret': True, 'required': True},
        ],
        # Read-only sync surfaced on demand from the Surveys page, not a
        # passive log_activity subscriber.
        'notify_tones': set(),
    },
    'linkedin_learning': {
        'label': 'LinkedIn Learning',
        'category': 'Talent',
        'description': 'Connect your LinkedIn Learning account to confirm live access to your course engagement data.',
        'setup_instructions': (
            'Generate a Reporting API application from your own LinkedIn Learning admin console '
            '(self-serve, no LinkedIn approval of Pulse needed):\n'
            '1. Log in to LinkedIn Learning and select "Go to Admin".\n'
            '2. In the side menu, select "Access content and reports via API" and expand '
            '"Generate LinkedIn Learning REST API Application".\n'
            '3. Click "Add application", name it (e.g. "Pulse Reporting"), and under "Choose keys" '
            'select "Report".\n'
            '4. Accept the terms, then copy the generated Client Id and Client Secret below.'
        ),
        'fields': [
            {'name': 'client_id', 'label': 'Client Id', 'type': 'text', 'secret': True, 'required': True},
            {'name': 'client_secret', 'label': 'Client Secret', 'type': 'password', 'secret': True, 'required': True},
        ],
        'notify_tones': set(),
    },
    'indeed': {
        'label': 'Indeed',
        'category': 'Talent',
        'description': 'Connect your Indeed Employer API credentials to confirm live access to your account.',
        'setup_instructions': (
            'This needs an Indeed Employer API app — Indeed\'s own docs describe getting one through '
            'their Partner Console after becoming an Indeed partner, so this may require your '
            'organization\'s existing Indeed partnership rather than a self-serve toggle:\n'
            '1. Sign in to Indeed\'s Partner Console with your Indeed account.\n'
            '2. Select your app from the dashboard and open the Credentials tab.\n'
            '3. Copy the Client ID and Client Secret below.\n'
            'If your organization doesn\'t have Partner Console access yet, that\'s the step to '
            'resolve with Indeed first — this form will tell you clearly if the credentials don\'t work.'
        ),
        'fields': [
            {'name': 'client_id', 'label': 'Client ID', 'type': 'text', 'secret': True, 'required': True},
            {'name': 'client_secret', 'label': 'Client Secret', 'type': 'password', 'secret': True, 'required': True},
        ],
        'notify_tones': set(),
    },
    'gusto': {
        'label': 'Gusto',
        'category': 'Payroll',
        'description': 'Connect a Gusto access token to confirm live access to your payroll account.',
        'setup_instructions': (
            'Gusto\'s API is OAuth-only (no static API key) and typically requires a Gusto Embedded '
            'Payroll partnership before it\'s usable in production — check with your Gusto contact if '
            'you\'re not sure your organization has this yet:\n'
            '1. Complete Gusto\'s OAuth authorization flow for your own registered Gusto app (via '
            'Gusto\'s developer docs) to obtain an access token.\n'
            '2. Paste that access token below.\n'
            'Gusto access tokens expire periodically — if the Test button here starts failing, '
            'generate a fresh token and reconnect.'
        ),
        'fields': [
            {'name': 'access_token', 'label': 'Access Token', 'type': 'password', 'secret': True, 'required': True},
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
