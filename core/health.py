"""Shared "health score" computation — org-wide (OrgHealthView) and
per-employee (MyDashboardView's "my work health") both reduce to the same
shape: a handful of named flag counts, deducted from a 100-point baseline.
Kept as one small function so the deduction weights only ever live in one
place."""

# Points deducted per flagged item, per flag type — an unresolved IT
# incident is a bigger drag than an open survey, so these aren't uniform.
FLAG_WEIGHTS = {
    'non_compliant_byod': 6,
    'unresolved_incidents': 5,
    'pending_recoveries': 3,
    'discrepancies_flagged': 8,
    'overdue_compliance': 6,
    'pending_leave': 2,
    'open_surveys': 1,
    'overdue_goals': 4,
    'awaiting_input_tickets': 5,
    'claims_under_review': 2,
    'goal_check_ins_due': 3,
    'compliance_acks_needed': 6,
}

FLAG_LABELS = {
    'non_compliant_byod': 'BYOD devices non-compliant',
    'unresolved_incidents': 'Unresolved IT incidents',
    'pending_recoveries': 'Pending asset recoveries',
    'discrepancies_flagged': 'Payroll discrepancies flagged',
    'overdue_compliance': 'Compliance filings overdue',
    'pending_leave': 'Leave requests pending',
    'open_surveys': 'Surveys still open',
    'overdue_goals': 'Goals overdue',
    'awaiting_input_tickets': 'Tickets awaiting your input',
    'claims_under_review': 'Claims under review',
    'goal_check_ins_due': 'Goal check-ins due',
    'compliance_acks_needed': 'Compliance acknowledgements needed',
}


def compute_health(counts_by_module):
    """`counts_by_module`: {module_label: {flag_key: count, ...}}. Returns
    {'score': int 0-100, 'flags': [{module, key, label, count}, ...]}
    (only non-zero flags are listed — a healthy org/employee shows an empty
    list, not a wall of zeroes)."""
    score = 100
    flags = []
    for module_label, counts in counts_by_module.items():
        for key, count in counts.items():
            if not count:
                continue
            score -= FLAG_WEIGHTS.get(key, 3) * count
            flags.append({'module': module_label, 'key': key, 'label': FLAG_LABELS.get(key, key), 'count': count})
    return {'score': max(0, score), 'flags': flags}
