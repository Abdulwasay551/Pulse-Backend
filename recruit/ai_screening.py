"""AI resume screening.

This is a keyword/skill-overlap heuristic, not a call to an LLM — wiring up
real AI scoring (e.g. an Anthropic/OpenAI call to read the resume and job
description and produce a fit assessment) needs an API key nobody has
provisioned for this project yet. This still gives a genuinely useful,
working score today, and the scoring function is isolated here so it's a
drop-in replacement later: same signature, same return shape.
"""

import re

_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+#.]{1,}")

_STOPWORDS = {
    'the', 'and', 'for', 'with', 'a', 'an', 'of', 'to', 'in', 'on', 'or', 'is',
    'are', 'be', 'as', 'at', 'by', 'this', 'that', 'will', 'you', 'your',
    'we', 'our', 'have', 'has', 'must', 'should', 'can', 'able', 'years',
    'year', 'experience', 'strong', 'excellent', 'good', 'skills',
}


def _keywords(text: str) -> set[str]:
    # The continuation class deliberately allows '+#.' mid-word (so "C++",
    # "C#", "Node.js" stay intact) but that also grabs a trailing sentence
    # period ("React.") — strip trailing punctuation after matching so that
    # doesn't silently fail to match the bare word "react" elsewhere.
    words = (w.lower().rstrip('.,;:!?') for w in _WORD_RE.findall(text or ''))
    return {w for w in words if w not in _STOPWORDS and len(w) > 2}


def score_candidate(resume_text: str, requisition_title: str, requirements: str) -> tuple[int, str]:
    """Returns (score 0-100, human-readable notes)."""
    resume_keywords = _keywords(resume_text)
    target_text = f'{requisition_title}\n{requirements}'
    target_keywords = _keywords(target_text)

    if not resume_keywords:
        return 0, 'No resume text on file — upload a resume or paste its text to screen this candidate.'
    if not target_keywords:
        return 50, 'No job requirements on file for this requisition — scored as a neutral baseline.'

    matched = sorted(resume_keywords & target_keywords)
    score = round(len(matched) / len(target_keywords) * 100) if target_keywords else 0
    score = max(0, min(100, score))

    if matched:
        shown = ', '.join(matched[:8])
        more = f' (+{len(matched) - 8} more)' if len(matched) > 8 else ''
        notes = f'Matched {len(matched)}/{len(target_keywords)} requirement keywords: {shown}{more}.'
    else:
        notes = 'No overlap found between the resume and this role\'s listed requirements.'

    return score, notes
