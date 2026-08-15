"""AI resume screening — real AI when the org has connected a provider
(ai_core), otherwise a clear "not configured" signal so the frontend shows
the locked/mock state instead of a fake result. The keyword-overlap
heuristic below now only powers that mock preview's sample-looking content;
it is never returned as a real score.
"""

import re

from ai_core.providers import AIProviderError, run_completion
from ai_core.registry import resolve_credential_for_feature

FEATURE_KEY = 'resume_screening'

SYSTEM_PROMPT = (
    "You screen a candidate's resume against a job requisition for a human recruiter. "
    "This is advisory only, not a hiring decision — the recruiter makes every call themselves; "
    "you are only surfacing a fit signal and its reasoning. Never state or imply whether the "
    "candidate should be hired. Respond with ONLY this JSON shape, no other text: "
    '{"score": <int 0-100>, "strengths": [<short phrases>], "gaps": [<short phrases>], "summary": <one sentence>}'
)

_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+#.]{1,}")

_STOPWORDS = {
    'the', 'and', 'for', 'with', 'a', 'an', 'of', 'to', 'in', 'on', 'or', 'is',
    'are', 'be', 'as', 'at', 'by', 'this', 'that', 'will', 'you', 'your',
    'we', 'our', 'have', 'has', 'must', 'should', 'can', 'able', 'years',
    'year', 'experience', 'strong', 'excellent', 'good', 'skills',
}


def _keywords(text: str) -> set[str]:
    words = (w.lower().rstrip('.,;:!?') for w in _WORD_RE.findall(text or ''))
    return {w for w in words if w not in _STOPWORDS and len(w) > 2}


def heuristic_preview(resume_text: str, requisition_title: str, requirements: str) -> dict:
    """The keyword-overlap score — used only to fill the AiFeatureGate's
    blurred mock-preview content when no AI provider is connected, so the
    "locked" state still looks like a plausible real result behind the
    blur rather than empty placeholders."""
    resume_keywords = _keywords(resume_text)
    target_keywords = _keywords(f'{requisition_title}\n{requirements}')
    matched = sorted(resume_keywords & target_keywords)
    score = round(len(matched) / len(target_keywords) * 100) if target_keywords else 50
    return {
        'score': max(0, min(100, score)),
        'strengths': matched[:5] or ['Sample strength A', 'Sample strength B'],
        'gaps': ['Sample gap A', 'Sample gap B'],
        'summary': 'Connect an AI provider to unlock a real assessment.',
    }


def score_candidate(owner_id, resume_text: str, requisition_title: str, requirements: str) -> dict:
    """Returns {'configured': bool, 'score': int|None, 'notes': str,
    'strengths': list[str], 'gaps': list[str]}. 'configured': False means no
    usable credential for this feature — callers must NOT fall back to the
    heuristic in that case; the frontend gate handles the locked state."""
    credential = resolve_credential_for_feature(owner_id, FEATURE_KEY)
    if credential is None:
        return {'configured': False, 'score': None, 'notes': '', 'strengths': [], 'gaps': []}
    if not resume_text:
        return {'configured': True, 'score': 0, 'notes': 'No resume text on file.', 'strengths': [], 'gaps': []}

    prompt = (
        f'Job title: {requisition_title}\nRequirements:\n{requirements[:4000]}\n\n'
        f'Resume:\n{resume_text[:8000]}'
    )
    try:
        result = run_completion(credential, system=SYSTEM_PROMPT, user_prompt=prompt, max_tokens=600)
    except AIProviderError as exc:
        return {
            'configured': True, 'score': None, 'notes': f'AI screening failed: {exc}',
            'strengths': [], 'gaps': [], 'error': True,
        }

    parsed = result['parsed'] or {}
    try:
        score = max(0, min(100, int(parsed.get('score', 0) or 0)))
    except (TypeError, ValueError):
        score = 0
    return {
        'configured': True,
        'score': score,
        'notes': str(parsed.get('summary', ''))[:500],
        'strengths': [str(s) for s in list(parsed.get('strengths', []))[:8]],
        'gaps': [str(g) for g in list(parsed.get('gaps', []))[:8]],
    }
