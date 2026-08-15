"""Single source of truth for every AI-powered feature in the product —
drives the model's `feature_key` choices, the settings-page override list,
and the `/api/ai/status/` gate response all at once. Adding a future AI
feature (e.g. a job-description generator) is a one-line addition here;
nothing else needs to change to make it show up everywhere this registry is
read from."""

AI_FEATURES = {
    'resume_screening': {'label': 'AI Resume Screening', 'module': 'Recruit'},
}

AI_FEATURE_CHOICES = [(key, value['label']) for key, value in AI_FEATURES.items()]
