import uuid
from datetime import date

from django.conf import settings
from django.db import models
from django.utils import timezone


class Client(models.Model):
    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Prospect', 'Prospect'),
        ('At risk', 'At risk'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='clients')
    name = models.CharField(max_length=150)
    industry = models.CharField(max_length=100, blank=True)
    contact_name = models.CharField(max_length=150, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_number = models.CharField(max_length=30, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Prospect')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class Requisition(models.Model):
    PRIORITY_CHOICES = [
        ('High', 'High'),
        ('Medium', 'Medium'),
        ('Low', 'Low'),
    ]
    STATUS_CHOICES = [
        ('Open', 'Open'),
        ('Interviewing', 'Interviewing'),
        ('Offer stage', 'Offer stage'),
        ('On hold', 'On hold'),
        ('Filled', 'Filled'),
    ]
    EMPLOYMENT_TYPE_CHOICES = [
        ('Full-time', 'Full-time'),
        ('Part-time', 'Part-time'),
        ('Contract', 'Contract'),
        ('Temporary', 'Temporary'),
    ]
    # Requisitions stop counting toward a client's "open roles" once they
    # land in one of these — everything else is still actively being worked.
    OPEN_STATUSES = ['Open', 'Interviewing', 'Offer stage']

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='requisitions')
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='requisitions')
    title = models.CharField(max_length=150)
    recruiter = models.CharField(max_length=150, blank=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='Medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Open')
    # Required skills/keywords, one per line or comma-separated — this is
    # what AI resume screening matches a candidate's resume_text against.
    requirements = models.TextField(blank=True)
    salary_min = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    salary_max = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    location = models.CharField(max_length=150, blank=True)
    employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_TYPE_CHOICES, default='Full-time')
    headcount = models.PositiveIntegerField(default=1)
    description = models.TextField(blank=True)
    hiring_manager = models.CharField(max_length=150, blank=True)
    posted_at = models.DateField(default=date.today)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class Candidate(models.Model):
    STAGE_CHOICES = [
        ('Sourced', 'Sourced'),
        ('Interview', 'Interview'),
        ('Offer', 'Offer'),
        ('Placed', 'Placed'),
        ('Rejected', 'Rejected'),
    ]
    SOURCE_CHOICES = [
        ('LinkedIn', 'LinkedIn'),
        ('Referral', 'Referral'),
        ('Job Board', 'Job Board'),
        ('Sourced', 'Sourced'),
        ('Other', 'Other'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='candidates')
    name = models.CharField(max_length=150)
    role = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    country = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    client = models.ForeignKey(
        Client, on_delete=models.SET_NULL, null=True, blank=True, related_name='candidates'
    )
    requisition = models.ForeignKey(
        Requisition, on_delete=models.SET_NULL, null=True, blank=True, related_name='candidates'
    )
    stage = models.CharField(max_length=20, choices=STAGE_CHOICES, default='Sourced')
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='Sourced')
    # Nullable — most candidates entered before this field existed (or
    # sourced via API integrations that don't report pay) have no salary on
    # record, shown as "Not set" rather than $0.
    current_salary = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    applied_at = models.DateField(default=date.today)
    # Set automatically the moment stage becomes "Placed" (see save()) — this
    # is what the placements-per-month trend is computed from, independent of
    # whatever applied_at was.
    placed_at = models.DateField(null=True, blank=True)
    # Resume Pool is just candidates viewed through this lens (no active
    # requisition) — see the frontend's /dashboard/resume-pool page — rather
    # than a separate duplicate model.
    resume_file = models.FileField(upload_to='resumes/%Y/%m/', null=True, blank=True)
    resume_text = models.TextField(
        blank=True, help_text='Plain-text resume content, used for AI screening keyword matching.'
    )
    ai_score = models.PositiveSmallIntegerField(null=True, blank=True)
    ai_score_notes = models.TextField(blank=True)
    ai_score_strengths = models.JSONField(default=list, blank=True)
    ai_score_gaps = models.JSONField(default=list, blank=True)
    # The Candidate Portal is a public, no-login status page for the
    # candidate themselves — this token is its unguessable key. Real
    # candidate accounts/auth would be a much bigger lift; a stable secret
    # link the recruiter can share gives most of the same value honestly.
    portal_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.stage == 'Placed' and not self.placed_at:
            self.placed_at = timezone.now().date()
        elif self.stage != 'Placed':
            self.placed_at = None
        super().save(*args, **kwargs)


class OfferLetterTemplate(models.Model):
    """A reusable offer-letter body a client can have on file per role, so
    drafting a new offer is "pick a template, adjust the details" instead of
    writing the letter from scratch every time."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='offer_letter_templates')
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='offer_letter_templates')
    role_title = models.CharField(max_length=150)
    body = models.TextField(help_text='The offer letter template content — used to pre-fill a new offer for this role.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['client__name', 'role_title']

    def __str__(self):
        return f'{self.client.name} — {self.role_title}'


class OfferLetter(models.Model):
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Sent', 'Sent'),
        ('Signed', 'Signed'),
        ('Declined', 'Declined'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='offer_letters')
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='offer_letters')
    job_title = models.CharField(max_length=150)
    salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    body = models.TextField(help_text='The offer letter content itself.')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Draft')
    sent_at = models.DateTimeField(null=True, blank=True)
    # Signature capture here is a manual "mark as signed" action, not a real
    # e-signature vendor integration (DocuSign/HelloSign etc.) — that needs
    # an account + API keys nobody has provisioned yet.
    signed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Offer — {self.candidate.name} ({self.job_title})'


class BackgroundCheck(models.Model):
    # Field name (check_type) is unchanged for schema stability — only the
    # choices and the user-facing label ("Screening Type") changed.
    CHECK_TYPE_CHOICES = [
        ('Education', 'Education'),
        ('Employment', 'Employment'),
        ('Criminal', 'Criminal'),
        ('EEC', 'Education + Employment + Criminal (EEC)'),
    ]
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('In Progress', 'In progress'),
        ('Cleared', 'Cleared'),
        ('Flagged', 'Flagged'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='background_checks')
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='background_checks')
    check_type = models.CharField(max_length=20, choices=CHECK_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    # Internal tracking only — wiring up a real vendor (Checkr, Sterling,
    # etc.) needs that vendor's account + API keys, which nobody has
    # provisioned yet. This still gives real workflow value: initiate,
    # track, and record the outcome.
    initiated_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_check_type_display()} — {self.candidate.name}'


class Onboarding(models.Model):
    STATUS_CHOICES = [
        ('Not Started', 'Not started'),
        ('In Progress', 'In progress'),
        ('Completed', 'Completed'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='onboardings')
    candidate = models.OneToOneField(Candidate, on_delete=models.CASCADE, related_name='onboarding')
    start_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Not Started')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Onboarding — {self.candidate.name}'


class OnboardingTask(models.Model):
    CATEGORY_CHOICES = [
        ('Joining Documentation', 'Joining documentation'),
        ('Orientation', 'Orientation'),
        ('Training Plan', 'Training plan and schedule'),
        ('Portal Access', 'Portal access and installations'),
        ('Probation Evaluation', 'Probation evaluation'),
        ('Device Assignment', 'Device assignment'),
    ]
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('In Progress', 'In progress'),
        ('Done', 'Done'),
    ]

    onboarding = models.ForeignKey(Onboarding, on_delete=models.CASCADE, related_name='tasks')
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    title = models.CharField(max_length=150)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    # Joining Documentation / Training Plan tasks can carry an uploaded file
    # (the doc itself / a training resource).
    document = models.FileField(upload_to='onboarding-documents/%Y/%m/', null=True, blank=True)
    # Category-specific structured extras (Portal Access -> system_or_tool,
    # Probation Evaluation -> outcome, Device Assignment -> device_category)
    # — a JSON blob rather than one nullable column per category per field,
    # since each category only ever uses its own single key.
    extra_fields = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'created_at']

    def __str__(self):
        return f'{self.category}: {self.title}'


class Offboarding(models.Model):
    STATUS_CHOICES = [
        ('Not Started', 'Not started'),
        ('In Progress', 'In progress'),
        ('Completed', 'Completed'),
    ]
    REHIRE_INTEREST_CHOICES = [
        ('Not Contacted', 'Not contacted'),
        ('Interested', 'Interested'),
        ('Not Interested', 'Not interested'),
        ('Rehired', 'Rehired'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='offboardings')
    candidate = models.OneToOneField(Candidate, on_delete=models.CASCADE, related_name='offboarding')
    last_working_day = models.DateField()
    reason = models.CharField(max_length=200, blank=True)
    rehire_eligible = models.BooleanField(default=True)
    # Structured alumni-pool tracking, on top of the free-form rehire_notes
    # below — "more selections" for the Rehire & Alumni Pool view.
    rehire_interest = models.CharField(max_length=20, choices=REHIRE_INTEREST_CHOICES, default='Not Contacted')
    rehire_last_contacted = models.DateField(null=True, blank=True)
    # Free-form tracking for the Rehire & Alumni Pool view — conversations,
    # interest level, whether they've been reached out to again, etc.
    rehire_notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Not Started')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Offboarding — {self.candidate.name}'


class OffboardingTask(models.Model):
    CATEGORY_CHOICES = [
        ('Documents Checklist', 'Documents checklist'),
        ('Access Status', 'Access status'),
        ('Hardware Clearance', 'Hardware clearance'),
    ]
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('In Progress', 'In progress'),
        ('Done', 'Done'),
    ]

    offboarding = models.ForeignKey(Offboarding, on_delete=models.CASCADE, related_name='tasks')
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    title = models.CharField(max_length=150)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    # Documents Checklist tasks can carry an uploaded file.
    document = models.FileField(upload_to='offboarding-documents/%Y/%m/', null=True, blank=True)
    # Access Status -> system_or_tool, Hardware Clearance -> device_category
    # — same reasoning as OnboardingTask.extra_fields.
    extra_fields = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'created_at']

    def __str__(self):
        return f'{self.category}: {self.title}'
