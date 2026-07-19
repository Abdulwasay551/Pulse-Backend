from wagtail import blocks

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
