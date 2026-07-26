"""Value-addition / performance scoring (EVO-Talent > Goals & Appraisal),
"powered by EVO-AI" per the spec. Like recruit/ai_screening.py, this is a
real, working heuristic today — not a stub — built as a drop-in-replaceable
placeholder for a future real ML/LLM-based scoring model, since no such
model or vendor account is provisioned for this project yet.

The heuristic: average goal completion (0-100) blended with average
appraisal rating (1-5, scaled to 0-100), weighted evenly. Either half is
skipped (not just zeroed) if the employee has no goals or no appraisals, so
a new hire with only goals set isn't unfairly penalized for lacking a
review yet.
"""


def compute_value_score(employee):
    goals = list(employee.goals.all())
    appraisals = list(employee.appraisals.all())

    parts = []
    notes = []

    if goals:
        goal_avg = sum(g.progress for g in goals) / len(goals)
        parts.append(goal_avg)
        notes.append(f'{len(goals)} goal{"s" if len(goals) != 1 else ""} averaging {round(goal_avg)}% complete')

    if appraisals:
        rating_avg = sum(a.overall_rating for a in appraisals) / len(appraisals)
        rating_score = (rating_avg - 1) / 4 * 100  # 1..5 -> 0..100
        parts.append(rating_score)
        notes.append(f'{len(appraisals)} appraisal{"s" if len(appraisals) != 1 else ""} averaging {round(rating_avg, 1)}/5')

    if not parts:
        return None, 'No goals or appraisals on file yet.'

    score = round(sum(parts) / len(parts))
    return score, '; '.join(notes) + '.'
