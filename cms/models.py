from django.db import models
from wagtail import blocks
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.api import APIField
from wagtail.contrib.settings.models import BaseSiteSetting, register_setting
from wagtail.fields import StreamField
from wagtail.models import Page
from wagtail.search import index
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet
from wagtail_headless_preview.models import HeadlessPreviewMixin

from .blocks import (
    ComparisonRowBlock,
    DemoRowBlock,
    FaqItemBlock,
    FooterColumnBlock,
    NotificationBlock,
    PlacementPointBlock,
    PricingTierBlock,
    ResourceRowBlock,
    RoleBlock,
    SkillBarBlock,
    StageCountBlock,
    StatItemBlock,
    TestimonialBlock,
    UseCaseBlock,
    WIDGET_TYPE_CHOICES,
)


# ---------------------------------------------------------------------------
# Snippets
# ---------------------------------------------------------------------------


class Product(index.Indexed, models.Model):
    """One module in the EvoHR suite. Shared between the homepage suite cards
    and the Solutions page deep-dive sections, so it's edited once."""

    sort_order = models.IntegerField(default=0)
    tag = models.CharField(max_length=40, help_text="e.g. CORE, PAYROLL, TECH STAFFING")
    name = models.CharField(max_length=60, help_text="e.g. EvoHR Payroll")
    short_description = models.TextField(help_text="Shown on the homepage suite cards")
    long_description = models.TextField(blank=True, help_text="Shown on the Solutions page")
    bullets = StreamField(
        [("bullet", blocks.CharBlock(max_length=140))],
        blank=True,
        help_text="Shown as a checklist on the Solutions page",
    )
    widget_type = models.CharField(max_length=20, choices=WIDGET_TYPE_CHOICES, default="none")
    widget_rows = StreamField([("row", DemoRowBlock())], blank=True)
    widget_stages = StreamField([("stage", StageCountBlock())], blank=True)
    widget_skills = StreamField([("skill", SkillBarBlock())], blank=True)

    panels = [
        FieldPanel("sort_order"),
        FieldPanel("tag"),
        FieldPanel("name"),
        FieldPanel("short_description"),
        FieldPanel("long_description"),
        FieldPanel("bullets"),
        MultiFieldPanel(
            [
                FieldPanel("widget_type"),
                FieldPanel("widget_rows"),
                FieldPanel("widget_stages"),
                FieldPanel("widget_skills"),
            ],
            heading="Mini-dashboard widget (demo data)",
        ),
    ]

    api_fields = [
        APIField("sort_order"),
        APIField("tag"),
        APIField("name"),
        APIField("short_description"),
        APIField("long_description"),
        APIField("bullets"),
        APIField("widget_type"),
        APIField("widget_rows"),
        APIField("widget_stages"),
        APIField("widget_skills"),
    ]

    search_fields = [
        index.SearchField("name"),
        index.SearchField("short_description"),
    ]

    class Meta:
        ordering = ["sort_order"]

    def __str__(self):
        return self.name


class ProductViewSet(SnippetViewSet):
    """Promotes Product to its own top-level sidebar icon (rather than being
    nested one click deeper under the generic "Snippets" menu item) — this is
    the CMS's most-edited content, so it should be the most discoverable."""

    model = Product
    menu_label = "Products"
    menu_icon = "grid"
    menu_order = 200
    add_to_admin_menu = True
    list_display = ["name", "tag", "sort_order"]


register_snippet(Product, viewset=ProductViewSet)


# ---------------------------------------------------------------------------
# Site-wide settings (shared chrome: nav badge, footer, default CTA banner)
# ---------------------------------------------------------------------------


@register_setting
class SiteSettings(BaseSiteSetting):
    footer_tagline = models.CharField(
        max_length=200, default="The recruitment CRM for agencies that place people for a living."
    )
    copyright_holder = models.CharField(max_length=120, default="EvoHR, Inc. All rights reserved.")
    footer_columns = StreamField([("column", FooterColumnBlock())], blank=True)

    cta_default_title = models.CharField(max_length=120, default="Put your desk on the record.")
    cta_default_subtitle = models.CharField(
        max_length=200,
        default="Start a free 30-day trial. No credit card, no setup calls required.",
    )

    panels = [
        FieldPanel("footer_tagline"),
        FieldPanel("copyright_holder"),
        FieldPanel("footer_columns"),
        MultiFieldPanel(
            [FieldPanel("cta_default_title"), FieldPanel("cta_default_subtitle")],
            heading="Default closing CTA banner",
        ),
    ]

    api_fields = [
        APIField("footer_tagline"),
        APIField("copyright_holder"),
        APIField("footer_columns"),
        APIField("cta_default_title"),
        APIField("cta_default_subtitle"),
    ]

    class Meta:
        verbose_name = "Site settings"


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


class HomePage(HeadlessPreviewMixin, Page):
    max_count = 1
    template = "cms/home_page.html"

    hero_eyebrow = models.CharField(
        max_length=120, default="Trusted by agency recruiters across 100+ countries!"
    )
    hero_heading_pre = models.CharField(max_length=120, default="The recruitment CRM built for")
    hero_heading_highlight = models.CharField(max_length=60, default="closing placements")
    hero_heading_post = models.CharField(max_length=120, default=", not chasing spreadsheets.")
    hero_subtitle = models.TextField(
        default="EvoHR brings your candidates, clients, and open requisitions into one system "
        "of record — so your desk runs on data, not memory."
    )
    hero_cta_primary_label = models.CharField(max_length=40, default="Book a Demo")
    hero_cta_secondary_label = models.CharField(max_length=40, default="Start a 30 Day Trial")
    hero_note = models.CharField(
        max_length=120, default="No credit card required · Cancel anytime"
    )

    dashboard_total_placements = models.IntegerField(default=31)
    dashboard_growth_label = models.CharField(max_length=20, default="+18% QoQ")
    dashboard_placements = StreamField([("point", PlacementPointBlock())], blank=True)
    dashboard_notifications = StreamField([("notification", NotificationBlock())], blank=True)
    dashboard_payroll_label = models.CharField(max_length=40, default="Payroll · Aug run")
    dashboard_payroll_amount = models.CharField(max_length=20, default="$186,400")
    dashboard_payroll_subtext = models.CharField(
        max_length=60, default="42 contractors · processed"
    )
    dashboard_payroll_status = models.CharField(max_length=30, default="Reconciled")
    dashboard_attendance_percent = models.IntegerField(default=93)
    dashboard_attendance_subtext = models.CharField(
        max_length=60, default="42 / 45 timesheets submitted"
    )

    trust_logos = StreamField([("logo", blocks.CharBlock(max_length=60))], blank=True)

    suite_eyebrow = models.CharField(max_length=60, default="The EvoHR suite")
    suite_title = models.CharField(
        max_length=160, default="One platform, every part of the desk."
    )
    suite_subtitle = models.TextField(
        default="Start with the core CRM, then turn on the modules your agency actually needs."
    )

    stats_heading = models.CharField(
        max_length=200, default="EvoHR makes closing placements effortless"
    )
    stats_items = StreamField([("stat", StatItemBlock())], blank=True)
    stats_cta_label = models.CharField(max_length=40, default="Book a demo")

    testimonials_eyebrow = models.CharField(max_length=60, default="What agencies say")
    testimonials_title = models.CharField(
        max_length=160, default="Recruiters run their whole desk on this."
    )
    testimonials = StreamField([("testimonial", TestimonialBlock())], blank=True)

    content_panels = Page.content_panels + [
        MultiFieldPanel(
            [
                FieldPanel("hero_eyebrow"),
                FieldPanel("hero_heading_pre"),
                FieldPanel("hero_heading_highlight"),
                FieldPanel("hero_heading_post"),
                FieldPanel("hero_subtitle"),
                FieldPanel("hero_cta_primary_label"),
                FieldPanel("hero_cta_secondary_label"),
                FieldPanel("hero_note"),
            ],
            heading="Hero",
        ),
        MultiFieldPanel(
            [
                FieldPanel("dashboard_total_placements"),
                FieldPanel("dashboard_growth_label"),
                FieldPanel("dashboard_placements"),
                FieldPanel("dashboard_notifications"),
                FieldPanel("dashboard_payroll_label"),
                FieldPanel("dashboard_payroll_amount"),
                FieldPanel("dashboard_payroll_subtext"),
                FieldPanel("dashboard_payroll_status"),
                FieldPanel("dashboard_attendance_percent"),
                FieldPanel("dashboard_attendance_subtext"),
            ],
            heading="Live dashboard visual (demo data)",
        ),
        FieldPanel("trust_logos"),
        MultiFieldPanel(
            [
                FieldPanel("suite_eyebrow"),
                FieldPanel("suite_title"),
                FieldPanel("suite_subtitle"),
            ],
            heading="Suite section header",
        ),
        MultiFieldPanel(
            [
                FieldPanel("stats_heading"),
                FieldPanel("stats_items"),
                FieldPanel("stats_cta_label"),
            ],
            heading="Stats banner (black section)",
        ),
        MultiFieldPanel(
            [
                FieldPanel("testimonials_eyebrow"),
                FieldPanel("testimonials_title"),
                FieldPanel("testimonials"),
            ],
            heading="Testimonials",
        ),
    ]

    api_fields = [
        APIField("hero_eyebrow"),
        APIField("hero_heading_pre"),
        APIField("hero_heading_highlight"),
        APIField("hero_heading_post"),
        APIField("hero_subtitle"),
        APIField("hero_cta_primary_label"),
        APIField("hero_cta_secondary_label"),
        APIField("hero_note"),
        APIField("dashboard_total_placements"),
        APIField("dashboard_growth_label"),
        APIField("dashboard_placements"),
        APIField("dashboard_notifications"),
        APIField("dashboard_payroll_label"),
        APIField("dashboard_payroll_amount"),
        APIField("dashboard_payroll_subtext"),
        APIField("dashboard_payroll_status"),
        APIField("dashboard_attendance_percent"),
        APIField("dashboard_attendance_subtext"),
        APIField("trust_logos"),
        APIField("suite_eyebrow"),
        APIField("suite_title"),
        APIField("suite_subtitle"),
        APIField("stats_heading"),
        APIField("stats_items"),
        APIField("stats_cta_label"),
        APIField("testimonials_eyebrow"),
        APIField("testimonials_title"),
        APIField("testimonials"),
    ]


class PricingPage(HeadlessPreviewMixin, Page):
    max_count = 1
    template = "cms/pricing_page.html"

    eyebrow = models.CharField(max_length=60, default="PRICING")
    heading = models.CharField(max_length=160, default="Priced per recruiter, not per headache.")
    subtitle = models.TextField(
        default="Every plan includes the core CRM and ATS. Add payroll, benefits, and "
        "mobility as your desk grows."
    )
    tiers = StreamField([("tier", PricingTierBlock())], blank=True)
    comparison_rows = StreamField([("row", ComparisonRowBlock())], blank=True)
    faq_items = StreamField([("item", FaqItemBlock())], blank=True)

    content_panels = Page.content_panels + [
        MultiFieldPanel(
            [FieldPanel("eyebrow"), FieldPanel("heading"), FieldPanel("subtitle")],
            heading="Header",
        ),
        FieldPanel("tiers"),
        FieldPanel("comparison_rows"),
        FieldPanel("faq_items"),
    ]

    api_fields = [
        APIField("eyebrow"),
        APIField("heading"),
        APIField("subtitle"),
        APIField("tiers"),
        APIField("comparison_rows"),
        APIField("faq_items"),
    ]


class SolutionsPage(HeadlessPreviewMixin, Page):
    max_count = 1
    template = "cms/solutions_page.html"

    eyebrow = models.CharField(max_length=60, default="SOLUTIONS")
    heading = models.CharField(
        max_length=160, default="Everything your desk needs, connected."
    )
    subtitle = models.TextField(
        default="Start with the core CRM, then turn on the modules your agency actually "
        "needs — each one shares the same candidate and client record."
    )

    content_panels = Page.content_panels + [
        MultiFieldPanel(
            [FieldPanel("eyebrow"), FieldPanel("heading"), FieldPanel("subtitle")],
            heading="Header",
        ),
    ]

    api_fields = [
        APIField("eyebrow"),
        APIField("heading"),
        APIField("subtitle"),
    ]


class UseCasesPage(HeadlessPreviewMixin, Page):
    max_count = 1
    template = "cms/use_cases_page.html"

    eyebrow = models.CharField(max_length=60, default="USE CASES")
    heading = models.CharField(max_length=160, default="Built for how your desk actually works.")
    subtitle = models.TextField(
        default="Four ways recruiting teams run their business on EvoHR — pick the shape "
        "that matches yours."
    )
    cases = StreamField([("case", UseCaseBlock())], blank=True)
    shift_eyebrow = models.CharField(max_length=60, default="The shift")
    shift_title = models.CharField(
        max_length=160, default="What changes the week you switch on."
    )
    before_items = StreamField([("item", blocks.CharBlock(max_length=140))], blank=True)
    after_items = StreamField([("item", blocks.CharBlock(max_length=140))], blank=True)

    content_panels = Page.content_panels + [
        MultiFieldPanel(
            [FieldPanel("eyebrow"), FieldPanel("heading"), FieldPanel("subtitle")],
            heading="Header",
        ),
        FieldPanel("cases"),
        MultiFieldPanel(
            [
                FieldPanel("shift_eyebrow"),
                FieldPanel("shift_title"),
                FieldPanel("before_items"),
                FieldPanel("after_items"),
            ],
            heading="Before / after comparison",
        ),
    ]

    api_fields = [
        APIField("eyebrow"),
        APIField("heading"),
        APIField("subtitle"),
        APIField("cases"),
        APIField("shift_eyebrow"),
        APIField("shift_title"),
        APIField("before_items"),
        APIField("after_items"),
    ]


class WhoWeServePage(HeadlessPreviewMixin, Page):
    max_count = 1
    template = "cms/who_we_serve_page.html"

    eyebrow = models.CharField(max_length=60, default="WHO WE SERVE")
    heading = models.CharField(max_length=160, default="One system, every seat on the team.")
    subtitle = models.TextField(
        default="Recruiters, ops, sales, and finance all work off the same record — just "
        "shaped around what each role actually needs."
    )
    roles = StreamField([("role", RoleBlock())], blank=True)

    content_panels = Page.content_panels + [
        MultiFieldPanel(
            [FieldPanel("eyebrow"), FieldPanel("heading"), FieldPanel("subtitle")],
            heading="Header",
        ),
        FieldPanel("roles"),
    ]

    api_fields = [
        APIField("eyebrow"),
        APIField("heading"),
        APIField("subtitle"),
        APIField("roles"),
    ]


class ResourcesPage(HeadlessPreviewMixin, Page):
    max_count = 1
    template = "cms/resources_page.html"

    eyebrow = models.CharField(max_length=60, default="RESOURCES")
    heading = models.CharField(
        max_length=160, default="Guides, playbooks, and help — all in one place."
    )
    subtitle = models.TextField(
        default="Everything to get your desk running on EvoHR, and keep it running well."
    )
    blog_posts = StreamField([("item", ResourceRowBlock())], blank=True)
    guides = StreamField([("item", ResourceRowBlock())], blank=True)
    help_articles = StreamField([("item", ResourceRowBlock())], blank=True)
    api_docs_title = models.CharField(max_length=100, default="Build on the EvoHR API")
    api_docs_description = models.CharField(
        max_length=200,
        default="REST endpoints for candidates, requisitions, placements, and payroll.",
    )
    api_docs_snippet = models.TextField(
        default='GET /v1/candidates/{id}\n{\n  "name": "Ava Thompson",\n  "stage": "interview",\n  "role": "Backend Engineer"\n}'
    )

    content_panels = Page.content_panels + [
        MultiFieldPanel(
            [FieldPanel("eyebrow"), FieldPanel("heading"), FieldPanel("subtitle")],
            heading="Header",
        ),
        FieldPanel("blog_posts"),
        FieldPanel("guides"),
        FieldPanel("help_articles"),
        MultiFieldPanel(
            [
                FieldPanel("api_docs_title"),
                FieldPanel("api_docs_description"),
                FieldPanel("api_docs_snippet"),
            ],
            heading="API docs card",
        ),
    ]

    api_fields = [
        APIField("eyebrow"),
        APIField("heading"),
        APIField("subtitle"),
        APIField("blog_posts"),
        APIField("guides"),
        APIField("help_articles"),
        APIField("api_docs_title"),
        APIField("api_docs_description"),
        APIField("api_docs_snippet"),
    ]
