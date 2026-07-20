import base64

from django import forms
from wagtail import blocks


class Base64ImageBlock(blocks.FieldBlock):
    """Renders as a plain file-upload field but stores the result as a
    base64 data URI string instead of using Wagtail's image/file storage —
    a deliberate stopgap so logo uploads work without wiring up external
    media storage (relevant on hosts like Vercel with an ephemeral
    filesystem). Fine for a handful of small logo images; not a general
    replacement for Wagtail's image chooser. Because file inputs can't be
    pre-filled, editing an existing entry without choosing a new file
    clears the stored image — re-upload it whenever you edit this block.
    """

    def __init__(self, required=False, help_text=None, **kwargs):
        self.field = forms.CharField(
            required=required,
            help_text=help_text,
            widget=forms.FileInput(),
        )
        super().__init__(**kwargs)

    def value_from_datadict(self, data, files, prefix):
        upload = files.get(prefix)
        if upload:
            content = upload.read()
            encoded = base64.b64encode(content).decode("ascii")
            mime = getattr(upload, "content_type", None) or "image/png"
            return f"data:{mime};base64,{encoded}"
        return ""

    def clean(self, value):
        return value or ""

TONE_CHOICES = [
    ("primary", "Primary / success (emerald)"),
    ("amber", "Amber / warning"),
    ("maroon", "Maroon / danger"),
    ("neutral", "Neutral / grey"),
]

WIDGET_TYPE_CHOICES = [
    ("none", "No widget"),
    ("pipeline", "Pipeline stage counts"),
    ("payroll", "Payroll runs list"),
    ("it", "Skill match bars"),
    ("benefits", "Benefits list"),
    ("hire", "Requisitions list"),
    ("mobility", "Mobility list"),
    ("deals", "Deals pipeline list"),
]

COMPARISON_VALUE_CHOICES = [
    ("yes", "Included"),
    ("partial", "Partial"),
    ("no", "Not included"),
]


class DemoRowBlock(blocks.StructBlock):
    """A single label/status/tone row, used by list-style mini-dashboard widgets."""

    label = blocks.CharBlock(max_length=80)
    status = blocks.CharBlock(max_length=40)
    tone = blocks.ChoiceBlock(choices=TONE_CHOICES, default="neutral")

    class Meta:
        icon = "list-ul"
        label = "Demo row"


class StageCountBlock(blocks.StructBlock):
    """A single pipeline-stage tile, e.g. 'Sourced · 12'."""

    label = blocks.CharBlock(max_length=40)
    count = blocks.IntegerBlock()

    class Meta:
        icon = "order"
        label = "Pipeline stage"


class SkillBarBlock(blocks.StructBlock):
    """A single skill-match progress bar, e.g. 'React · 92%'."""

    label = blocks.CharBlock(max_length=40)
    percent = blocks.IntegerBlock(min_value=0, max_value=100)

    class Meta:
        icon = "success"
        label = "Skill bar"


class RoleBlock(blocks.StructBlock):
    """One 'who we serve' segment: a role, its pitch, and its demo widget."""

    tag = blocks.CharBlock(max_length=40, help_text="e.g. AGENCY RECRUITERS")
    title = blocks.CharBlock(max_length=120)
    description = blocks.TextBlock()
    bullets = blocks.ListBlock(blocks.CharBlock(max_length=140))
    widget_type = blocks.ChoiceBlock(choices=WIDGET_TYPE_CHOICES, default="none", required=False)
    widget_rows = blocks.ListBlock(DemoRowBlock(), required=False)
    widget_stages = blocks.ListBlock(StageCountBlock(), required=False)
    widget_skills = blocks.ListBlock(SkillBarBlock(), required=False)

    class Meta:
        icon = "user"
        label = "Role"


class UseCaseBlock(blocks.StructBlock):
    tag = blocks.CharBlock(max_length=40, help_text="e.g. STAFFING AGENCIES")
    title = blocks.CharBlock(max_length=160)
    description = blocks.TextBlock()
    stat = blocks.CharBlock(max_length=20, help_text="e.g. 3.2x")
    stat_label = blocks.CharBlock(max_length=60, help_text="e.g. faster time-to-fill")
    bullets = blocks.ListBlock(blocks.CharBlock(max_length=140))

    class Meta:
        icon = "help"
        label = "Use case"


class PricingTierBlock(blocks.StructBlock):
    name = blocks.CharBlock(max_length=40)
    description = blocks.CharBlock(max_length=160)
    is_custom = blocks.BooleanBlock(
        required=False, help_text="Tick for a 'Custom / talk to sales' tier with no price"
    )
    monthly_price = blocks.IntegerBlock(required=False)
    annual_price = blocks.IntegerBlock(required=False, help_text="Effective monthly price when billed annually")
    featured = blocks.BooleanBlock(required=False, help_text="Highlight as 'Most popular'")
    cta_label = blocks.CharBlock(max_length=40, default="Start free trial")
    features = blocks.ListBlock(blocks.CharBlock(max_length=140))

    class Meta:
        icon = "pick"
        label = "Pricing tier"


class ComparisonRowBlock(blocks.StructBlock):
    feature = blocks.CharBlock(max_length=140)
    starter = blocks.ChoiceBlock(choices=COMPARISON_VALUE_CHOICES, default="no")
    growth = blocks.ChoiceBlock(choices=COMPARISON_VALUE_CHOICES, default="no")
    enterprise = blocks.ChoiceBlock(choices=COMPARISON_VALUE_CHOICES, default="yes")

    class Meta:
        icon = "table"
        label = "Comparison row"


class FaqItemBlock(blocks.StructBlock):
    question = blocks.CharBlock(max_length=200)
    answer = blocks.TextBlock()

    class Meta:
        icon = "help"
        label = "FAQ item"


class ResourceRowBlock(blocks.StructBlock):
    title = blocks.CharBlock(max_length=160)
    meta = blocks.CharBlock(max_length=60, help_text="e.g. 'Jul 12 · 6 min read' or '12.4k views'")

    class Meta:
        icon = "doc-full"
        label = "Resource item"


class PlacementPointBlock(blocks.StructBlock):
    month = blocks.CharBlock(max_length=10, help_text="e.g. Feb")
    value = blocks.IntegerBlock()

    class Meta:
        icon = "order"
        label = "Chart point"


class NotificationBlock(blocks.StructBlock):
    initials = blocks.CharBlock(max_length=3)
    name = blocks.CharBlock(max_length=80)
    role = blocks.CharBlock(max_length=100)
    status = blocks.CharBlock(max_length=40)
    tone = blocks.ChoiceBlock(choices=TONE_CHOICES, default="primary")

    class Meta:
        icon = "user"
        label = "Notification"


class FooterColumnBlock(blocks.StructBlock):
    heading = blocks.CharBlock(max_length=40)
    url = blocks.CharBlock(max_length=200)
    links = blocks.ListBlock(blocks.CharBlock(max_length=60))

    class Meta:
        icon = "list-ul"
        label = "Footer column"


class StatItemBlock(blocks.StructBlock):
    value = blocks.CharBlock(max_length=20, help_text="e.g. 150+, $20B+, 94%")
    label = blocks.CharBlock(max_length=60, help_text="e.g. countries, client retention")

    class Meta:
        icon = "site"
        label = "Stat"


class TestimonialBlock(blocks.StructBlock):
    quote = blocks.TextBlock(max_length=280, help_text="Keep it specific and outcome-based")
    name = blocks.CharBlock(max_length=80)
    title = blocks.CharBlock(max_length=100, help_text="e.g. Founder, Bright Path Staffing")
    initials = blocks.CharBlock(max_length=3)

    class Meta:
        icon = "openquote"
        label = "Testimonial"


class TrustLogoBlock(blocks.StructBlock):
    name = blocks.CharBlock(max_length=60, help_text="Company name, used as image alt text")
    logo_url = blocks.URLBlock(
        required=False, help_text="Direct URL to the logo image (SVG or PNG) — use this OR upload below"
    )
    logo_upload = Base64ImageBlock(
        required=False, help_text="Or upload a logo image directly (stored inline, see note above)"
    )

    class Meta:
        icon = "image"
        label = "Trust logo"
