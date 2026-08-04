from django.conf import settings
from django.db import models


class Goal(models.Model):
    """Goal Setting & KPIs (EVO-Talent > Goals & Appraisal)."""

    STATUS_CHOICES = [
        ('Not Started', 'Not started'),
        ('In Progress', 'In progress'),
        ('Completed', 'Completed'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='goals')
    employee = models.ForeignKey('people.Employee', on_delete=models.CASCADE, related_name='goals')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    target_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Not Started')
    progress = models.PositiveSmallIntegerField(default=0, help_text='0–100% complete.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.employee.name}: {self.title}'


class Appraisal(models.Model):
    """Performance Appraisals based on yearly 360° feedback (EVO-Talent >
    Goals & Appraisal)."""

    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Submitted', 'Submitted'),
        ('Finalized', 'Finalized'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='appraisals')
    employee = models.ForeignKey('people.Employee', on_delete=models.CASCADE, related_name='appraisals')
    period = models.CharField(max_length=100, help_text='e.g. "2026 Annual Review".')
    reviewer = models.CharField(max_length=150, blank=True)
    overall_rating = models.PositiveSmallIntegerField(help_text='1–5.')
    strengths = models.TextField(blank=True)
    areas_for_improvement = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.employee.name} — {self.period}'


class CompetencyRating(models.Model):
    """Competency Mapping of Employees (Goals & Appraisal) *and* Skills &
    Competency Mapping (Learning & Growth) — the spec lists the same idea
    under both headings, so one model backs both sidebar entries, same
    pattern as Recruit's AI Resume Screening pointing at the Resume Pool
    page."""

    LEVEL_CHOICES = [(i, str(i)) for i in range(1, 6)]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='competency_ratings')
    employee = models.ForeignKey('people.Employee', on_delete=models.CASCADE, related_name='competency_ratings')
    competency = models.CharField(max_length=150)
    level = models.PositiveSmallIntegerField(choices=LEVEL_CHOICES, default=1)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['employee__name', 'competency']

    def __str__(self):
        return f'{self.employee.name}: {self.competency} ({self.level}/5)'


class Course(models.Model):
    """Training & Learning Management System (LMS) (EVO-Talent > Learning &
    Growth)."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='courses')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    duration_hours = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['title']

    def __str__(self):
        return self.title


class Enrollment(models.Model):
    STATUS_CHOICES = [
        ('Not Started', 'Not started'),
        ('In Progress', 'In progress'),
        ('Completed', 'Completed'),
    ]

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    employee = models.ForeignKey('people.Employee', on_delete=models.CASCADE, related_name='enrollments')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Not Started')
    completed_at = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = [('course', 'employee')]

    def __str__(self):
        return f'{self.employee.name} → {self.course.title}'


class CareerPath(models.Model):
    """Career Development Paths, mapped per department hierarchy (EVO-Talent
    > Learning & Growth)."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='career_paths')
    employee = models.ForeignKey('people.Employee', on_delete=models.CASCADE, related_name='career_paths')
    current_role = models.CharField(max_length=150, blank=True)
    target_role = models.CharField(max_length=150, blank=True)
    department = models.CharField(max_length=100, blank=True)
    milestones = models.TextField(blank=True, help_text='Key steps/skills needed to reach the target role.')
    target_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.employee.name}: {self.current_role} → {self.target_role}'


class SuccessionPlan(models.Model):
    """Succession Planning / 9-Box Grid (EVO-Talent > Learning & Growth) —
    potential × performance (Low/Medium/High each) places the employee on
    the 9-box grid; the grid itself is derived/rendered on the frontend, not
    stored."""

    RATING_CHOICES = [
        ('Low', 'Low'),
        ('Medium', 'Medium'),
        ('High', 'High'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='succession_plans')
    employee = models.ForeignKey('people.Employee', on_delete=models.CASCADE, related_name='succession_plans')
    potential_rating = models.CharField(max_length=10, choices=RATING_CHOICES, default='Medium')
    performance_rating = models.CharField(max_length=10, choices=RATING_CHOICES, default='Medium')
    successor_notes = models.TextField(blank=True)
    ready_now = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f'{self.employee.name}: {self.potential_rating} potential / {self.performance_rating} performance'


class RecruiterFeedback(models.Model):
    """Recruiter → HR feedback notes on a placed/hired employee — mirrors
    people.Recognition's free-text "who said this" pattern (given_by is a
    plain string, not a FK back to the submitting login)."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='recruiter_feedback')
    employee = models.ForeignKey('people.Employee', on_delete=models.CASCADE, related_name='recruiter_feedback')
    given_by = models.CharField(max_length=150, blank=True)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Feedback for {self.employee.name}'
