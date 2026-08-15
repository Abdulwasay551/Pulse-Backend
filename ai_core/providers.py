"""One dispatch function per provider family, over plain `requests` calls —
no per-provider SDK dependency. OpenAI/OpenRouter/DeepSeek/any generic
"openai_compatible" endpoint all speak the same chat-completions shape, so
they share one implementation; Anthropic and Gemini get their own request/
response handling.

Every `_run_*` function returns {'text': str, 'parsed': dict | None} and
raises AIProviderError — never a raw requests exception, never the provider's
raw response body or the API key — on any failure, so callers can always
degrade to a clean, user-safe message."""

import json
import re

import requests

REQUEST_TIMEOUT = (5, 20)  # (connect, read) — see vercel.json's function maxDuration

OPENAI_COMPATIBLE_ENDPOINTS = {
    'openai': 'https://api.openai.com/v1/chat/completions',
    'openrouter': 'https://openrouter.ai/api/v1/chat/completions',
    'deepseek': 'https://api.deepseek.com/chat/completions',
}
ANTHROPIC_URL = 'https://api.anthropic.com/v1/messages'
GEMINI_URL_TMPL = 'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'

PROVIDER_CATALOG = {
    'openai': {
        'label': 'OpenAI',
        'requires_base_url': False,
        'suggested_models': ['gpt-5.1', 'gpt-5.1-mini', 'gpt-4.1', 'gpt-4.1-mini'],
    },
    'anthropic': {
        'label': 'Anthropic (Claude)',
        'requires_base_url': False,
        'suggested_models': ['claude-sonnet-5', 'claude-opus-5', 'claude-haiku-4-5-20251001'],
    },
    'google': {
        'label': 'Google (Gemini)',
        'requires_base_url': False,
        'suggested_models': ['gemini-2.5-pro', 'gemini-2.5-flash'],
    },
    'openrouter': {
        'label': 'OpenRouter',
        'requires_base_url': False,
        'suggested_models': ['openai/gpt-5.1', 'anthropic/claude-sonnet-5', 'google/gemini-2.5-flash'],
    },
    'deepseek': {
        'label': 'DeepSeek',
        'requires_base_url': False,
        'suggested_models': ['deepseek-chat', 'deepseek-reasoner'],
    },
    'openai_compatible': {
        'label': 'Other (OpenAI-compatible)',
        'requires_base_url': True,
        'suggested_models': [],
    },
}


class AIProviderError(Exception):
    """Message is always safe to show directly in the UI."""


def _extract_json(text: str) -> dict | None:
    """Strips ```json fences some providers add despite instructions, then
    parses. Returns None (not an exception) on failure — callers treat a
    missing `parsed` result as "answer arrived but wasn't usable JSON",
    which is recoverable, not fatal."""
    cleaned = re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip(), flags=re.MULTILINE)
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        return None


def _raise_for_status(resp):
    if resp.status_code in (401, 403):
        raise AIProviderError('The API key was rejected — check it in Settings, AI Integrations.')
    if resp.status_code == 429:
        raise AIProviderError('Rate limited by the provider — try again shortly.')
    if not resp.ok:
        raise AIProviderError('The AI provider returned an error.')


def _post(url, *, headers, json_body):
    try:
        resp = requests.post(url, headers=headers, json=json_body, timeout=REQUEST_TIMEOUT)
    except requests.Timeout as exc:
        raise AIProviderError("The AI provider didn't respond in time.") from exc
    except requests.RequestException as exc:
        raise AIProviderError('Could not reach the AI provider.') from exc
    _raise_for_status(resp)
    try:
        return resp.json()
    except ValueError as exc:
        raise AIProviderError('The AI provider returned an unexpected response.') from exc


def _run_openai_compatible(credential, api_key, system, user_prompt, json_mode, max_tokens):
    url = credential.base_url or OPENAI_COMPATIBLE_ENDPOINTS.get(credential.provider)
    if not url:
        raise AIProviderError('No endpoint configured for this provider.')
    body = {
        'model': credential.model,
        'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user_prompt}],
        'max_tokens': max_tokens,
    }
    if json_mode:
        body['response_format'] = {'type': 'json_object'}
    data = _post(url, headers={'Authorization': f'Bearer {api_key}'}, json_body=body)
    try:
        text = data['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError) as exc:
        raise AIProviderError('The AI provider returned an unexpected response.') from exc
    return {'text': text, 'parsed': _extract_json(text) if json_mode else None}


def _run_anthropic(credential, api_key, system, user_prompt, json_mode, max_tokens):
    body = {
        'model': credential.model,
        'system': system,
        'max_tokens': max_tokens,
        'messages': [{'role': 'user', 'content': user_prompt}],
    }
    data = _post(
        ANTHROPIC_URL,
        headers={'x-api-key': api_key, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'},
        json_body=body,
    )
    try:
        text = ''.join(block.get('text', '') for block in data['content'] if block.get('type') == 'text')
    except (KeyError, TypeError) as exc:
        raise AIProviderError('The AI provider returned an unexpected response.') from exc
    return {'text': text, 'parsed': _extract_json(text) if json_mode else None}


def _run_gemini(credential, api_key, system, user_prompt, json_mode, max_tokens):
    url = GEMINI_URL_TMPL.format(model=credential.model)
    generation_config = {'maxOutputTokens': max_tokens}
    if json_mode:
        generation_config['responseMimeType'] = 'application/json'
    body = {
        'contents': [{'role': 'user', 'parts': [{'text': user_prompt}]}],
        'systemInstruction': {'parts': [{'text': system}]},
        'generationConfig': generation_config,
    }
    data = _post(f'{url}?key={api_key}', headers={'content-type': 'application/json'}, json_body=body)
    try:
        parts = data['candidates'][0]['content']['parts']
        text = ''.join(p.get('text', '') for p in parts)
    except (KeyError, IndexError, TypeError) as exc:
        raise AIProviderError('The AI provider returned an unexpected response.') from exc
    return {'text': text, 'parsed': _extract_json(text) if json_mode else None}


_DISPATCH = {
    'openai': _run_openai_compatible,
    'openrouter': _run_openai_compatible,
    'deepseek': _run_openai_compatible,
    'openai_compatible': _run_openai_compatible,
    'anthropic': _run_anthropic,
    'google': _run_gemini,
}


def run_completion(credential, *, system: str, user_prompt: str, json_mode: bool = True, max_tokens: int = 800) -> dict:
    """Returns {'text': str, 'parsed': dict | None}. Raises AIProviderError
    on any failure — callers must catch it and degrade gracefully."""
    dispatch = _DISPATCH.get(credential.provider)
    if dispatch is None:
        raise AIProviderError(f'Unsupported provider: {credential.provider}')
    api_key = credential.get_api_key()
    return dispatch(credential, api_key, system, user_prompt, json_mode, max_tokens)
