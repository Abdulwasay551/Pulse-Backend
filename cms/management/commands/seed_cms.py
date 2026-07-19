from django.core.management.base import BaseCommand
from wagtail.models import Page, Site

from cms.models import (
    HomePage,
    PricingPage,
    Product,
    ResourcesPage,
    SiteSettings,
    SolutionsPage,
    UseCasesPage,
    WhoWeServePage,
)


def rows(*items):
    """[(label, status, tone), ...] -> StreamField raw value for widget_rows."""
    return [("row", {"label": label, "status": status, "tone": tone}) for label, status, tone in items]


def stages(*items):
    return [("stage", {"label": label, "count": count}) for label, count in items]


def skills(*items):
    return [("skill", {"label": label, "percent": percent}) for label, percent in items]


def bullets(*items):
    return [("bullet", text) for text in items]


PRODUCTS = [
    dict(
        sort_order=0,
        tag="CORE",
        name="EvoHR",
        short_description="Your recruitment CRM & ATS — candidates, clients, pipelines, and placements in one record.",
        long_description="The system of record for your desk — every candidate, client, and requisition connected to the same pipeline.",
        bullets=bullets(
            "Kanban and list pipeline views per job order",
            "Client and candidate records with full activity history",
            "Custom pipeline stages per desk or vertical",
        ),
        widget_type="pipeline",
        widget_stages=stages(("Sourced", 12), ("Interview", 6), ("Offer", 2), ("Placed", 3)),
    ),
    dict(
        sort_order=1,
        tag="PAYROLL",
        name="EvoHR Payroll",
        short_description="Automated pay runs and invoicing for contractors, temps, and permanent placements.",
        long_description="Run contractor and permanent placement payroll without re-keying a single timesheet.",
        bullets=bullets(
            "Automated pay runs reconciled against logged hours",
            "Placement fee invoicing generated from won deals",
            "Multi-currency payouts for international contractors",
        ),
        widget_type="payroll",
        widget_rows=rows(
            ("July payroll run", "Reconciled", "primary"),
            ("Contractor batch #14", "Needs review", "amber"),
            ("Bonus disbursement", "Reconciled", "primary"),
        ),
    ),
    dict(
        sort_order=2,
        tag="TECH STAFFING",
        name="EvoHR IT",
        short_description="A dedicated pipeline and skills matching layer built for technical and IT staffing desks.",
        long_description="A skills-matching layer purpose-built for technical and IT staffing desks under pressure to fill fast.",
        bullets=bullets(
            "Parsed skill extraction from resumes and profiles",
            "Match scoring against job requirements",
            "Technical assessment tracking per candidate",
        ),
        widget_type="it",
        widget_skills=skills(("React", 92), ("AWS", 95), ("Kubernetes", 87)),
    ),
    dict(
        sort_order=3,
        tag="BENEFITS",
        name="EvoHR Benefits",
        short_description="Benefits enrollment and administration for placed and contract talent, handled for you.",
        long_description="Benefits enrollment and administration for placed and contract talent, without the paperwork chase.",
        bullets=bullets(
            "Self-serve enrollment for placed candidates",
            "Plan comparisons and eligibility rules built in",
            "Renewal and life-event reminders, automated",
        ),
        widget_type="benefits",
        widget_rows=rows(
            ("Health insurance", "Enrolled", "primary"),
            ("Dental & vision", "Pending", "amber"),
            ("401(k) match", "Enrolled", "primary"),
        ),
    ),
    dict(
        sort_order=4,
        tag="CLIENT PORTAL",
        name="EvoHR Hire",
        short_description="A branded hiring portal where clients raise requisitions and review candidates directly.",
        long_description="A branded portal where clients raise requisitions, review shortlists, and leave feedback — no email chains.",
        bullets=bullets(
            "Clients submit and track requisitions themselves",
            "Shared candidate shortlists with inline feedback",
            "Full white-label branding on the client's domain",
        ),
        widget_type="hire",
        widget_rows=rows(
            ("Acme Corp · 4 roles", "Reviewing", "amber"),
            ("Globex · 2 roles", "Shortlisted", "primary"),
            ("Initech · 1 role", "New", "neutral"),
        ),
    ),
    dict(
        sort_order=5,
        tag="GLOBAL MOBILITY",
        name="EvoHR Mobility",
        short_description="Visa, relocation, and compliance tracking for cross-border and international placements.",
        long_description="Visa, relocation, and compliance tracking for placements that cross a border.",
        bullets=bullets(
            "Visa status and document tracking per placement",
            "Country-by-country compliance checklists",
            "Relocation milestones shared with the candidate",
        ),
        widget_type="mobility",
        widget_rows=rows(
            ("🇩🇪 Berlin relocation", "Visa approved", "primary"),
            ("🇸🇬 Singapore transfer", "Pending", "amber"),
            ("🇨🇦 Toronto relocation", "In progress", "neutral"),
        ),
    ),
]


class Command(BaseCommand):
    help = "Seed the CMS page tree, snippets, and site settings with EvoHR's current default copy."

    def handle(self, *args, **options):
        if HomePage.objects.exists():
            self.stdout.write(self.style.WARNING("HomePage already exists — skipping seed."))
            return

        root = Page.objects.get(id=1)
        try:
            welcome_page = Page.objects.get(id=2)
            if welcome_page.specific_class is Page:
                welcome_page.delete()
        except Page.DoesNotExist:
            pass

        home = HomePage(
            title="Home",
            slug="home",
            hero_eyebrow="Trusted by agency recruiters across 100+ countries!",
            hero_heading_pre="The recruitment CRM built for",
            hero_heading_highlight="closing placements",
            hero_heading_post=", not chasing spreadsheets.",
            hero_subtitle=(
                "EvoHR brings your candidates, clients, and open requisitions into one "
                "system of record — so your desk runs on data, not memory."
            ),
            hero_cta_primary_label="Book a Demo",
            hero_cta_secondary_label="Start a 30 Day Trial",
            hero_note="No credit card required · Cancel anytime",
            dashboard_total_placements=31,
            dashboard_growth_label="+18% QoQ",
            dashboard_placements=[
                ("point", {"month": "Feb", "value": 14}),
                ("point", {"month": "Mar", "value": 18}),
                ("point", {"month": "Apr", "value": 16}),
                ("point", {"month": "May", "value": 22}),
                ("point", {"month": "Jun", "value": 26}),
                ("point", {"month": "Jul", "value": 31}),
            ],
            dashboard_notifications=[
                (
                    "notification",
                    {
                        "initials": "AT",
                        "name": "Ava Thompson",
                        "role": "Senior Backend Engineer",
                        "status": "New application",
                        "tone": "primary",
                    },
                ),
                (
                    "notification",
                    {
                        "initials": "MR",
                        "name": "Marcus Reed",
                        "role": "Field Sales Rep — West",
                        "status": "Interviewing",
                        "tone": "amber",
                    },
                ),
                (
                    "notification",
                    {
                        "initials": "PN",
                        "name": "Priya Nair",
                        "role": "DevOps Lead",
                        "status": "Offer sent",
                        "tone": "primary",
                    },
                ),
                (
                    "notification",
                    {
                        "initials": "DA",
                        "name": "Diego Alvarez",
                        "role": "Support Engineer",
                        "status": "Not a fit",
                        "tone": "maroon",
                    },
                ),
                (
                    "notification",
                    {
                        "initials": "LN",
                        "name": "Lena Novak",
                        "role": "People Ops Coordinator",
                        "status": "Placed",
                        "tone": "primary",
                    },
                ),
            ],
            dashboard_payroll_label="Payroll · Aug run",
            dashboard_payroll_amount="$186,400",
            dashboard_payroll_subtext="42 contractors · processed",
            dashboard_payroll_status="Reconciled",
            dashboard_attendance_percent=93,
            dashboard_attendance_subtext="42 / 45 timesheets submitted",
            trust_logos=[
                ("logo", name)
                for name in [
                    "Northbridge Talent",
                    "Fernwood Staffing",
                    "Anchorpoint Search",
                    "Duskline Partners",
                    "Cascade Recruiting",
                    "Harborview Group",
                    "Meridian Staffing",
                    "Silverline Talent",
                ]
            ],
            suite_eyebrow="The EvoHR suite",
            suite_title="One platform, every part of the desk.",
            suite_subtitle="Start with the core CRM, then turn on the modules your agency actually needs.",
            stats_heading="EvoHR makes closing placements effortless",
            stats_items=[
                ("stat", {"value": "100+", "label": "countries"}),
                ("stat", {"value": "12,000+", "label": "recruiters"}),
                ("stat", {"value": "$2B+", "label": "placements facilitated"}),
                ("stat", {"value": "94%", "label": "client retention"}),
            ],
            stats_cta_label="Book a demo",
            testimonials_eyebrow="What agencies say",
            testimonials_title="Recruiters run their whole desk on this.",
            testimonials=[
                (
                    "testimonial",
                    {
                        "quote": "We cut time-to-placement by 30% in the first quarter — mostly by killing the "
                        "spreadsheet handoffs between sourcing and payroll.",
                        "name": "Priya Nair",
                        "title": "Founder, Anchorpoint Search",
                        "initials": "PN",
                    },
                ),
                (
                    "testimonial",
                    {
                        "quote": "Payroll used to eat a full day every two weeks. Now it's a review-and-approve "
                        "step that takes twenty minutes.",
                        "name": "Marcus Webb",
                        "title": "Operations Lead, Harborview Group",
                        "initials": "MW",
                    },
                ),
                (
                    "testimonial",
                    {
                        "quote": "Every recruiter on the desk works off the same candidate record now. No more "
                        "'whose version of this spreadsheet is current.'",
                        "name": "Elena Cho",
                        "title": "Managing Director, Meridian Staffing",
                        "initials": "EC",
                    },
                ),
            ],
        )
        root.add_child(instance=home)

        site, _ = Site.objects.update_or_create(
            is_default_site=True,
            defaults={"hostname": "localhost", "port": 8000, "root_page": home},
        )

        pricing = PricingPage(
            title="Pricing",
            slug="pricing",
            eyebrow="PRICING",
            heading="Priced per recruiter, not per headache.",
            subtitle=(
                "Every plan includes the core CRM and ATS. Add payroll, benefits, and "
                "mobility as your desk grows."
            ),
            tiers=[
                (
                    "tier",
                    {
                        "name": "Starter",
                        "description": "For solo recruiters and small desks getting off spreadsheets.",
                        "is_custom": False,
                        "monthly_price": 35,
                        "annual_price": 28,
                        "featured": False,
                        "cta_label": "Start free trial",
                        "features": [
                            "Core recruitment CRM & ATS",
                            "Candidate and client records",
                            "Basic pipeline reporting",
                            "Email support",
                        ],
                    },
                ),
                (
                    "tier",
                    {
                        "name": "Growth",
                        "description": "For agencies scaling past a handful of desks.",
                        "is_custom": False,
                        "monthly_price": 65,
                        "annual_price": 52,
                        "featured": True,
                        "cta_label": "Start free trial",
                        "features": [
                            "Everything in Starter",
                            "EvoHR Hire client portal",
                            "Contractor payroll & invoicing",
                            "Pipeline automation & sequences",
                            "Priority support",
                        ],
                    },
                ),
                (
                    "tier",
                    {
                        "name": "Enterprise",
                        "description": "For multi-country agencies and executive search firms.",
                        "is_custom": True,
                        "featured": False,
                        "cta_label": "Talk to sales",
                        "features": [
                            "Everything in Growth",
                            "Global mobility & visa tracking",
                            "Multi-country payroll & compliance",
                            "SSO, custom roles & API access",
                            "Dedicated success manager",
                        ],
                    },
                ),
            ],
            comparison_rows=[
                ("row", {"feature": f, "starter": s, "growth": g, "enterprise": e})
                for f, s, g, e in [
                    ("Candidates & clients CRM", "yes", "yes", "yes"),
                    ("Job pipeline & ATS", "yes", "yes", "yes"),
                    ("Client hiring portal (EvoHR Hire)", "no", "yes", "yes"),
                    ("Contractor payroll & invoicing", "no", "yes", "yes"),
                    ("Benefits administration", "no", "partial", "yes"),
                    ("IT / tech skill matching", "no", "partial", "yes"),
                    ("Global mobility & visas", "no", "no", "yes"),
                    ("API access & webhooks", "no", "partial", "yes"),
                    ("SSO & custom roles", "no", "no", "yes"),
                    ("Support", "no", "no", "yes"),
                ]
            ],
            faq_items=[
                (
                    "item",
                    {
                        "question": "How is pricing calculated?",
                        "answer": (
                            "You pay per active recruiter seat, not per candidate or client "
                            "record — so your database can grow freely without affecting your bill."
                        ),
                    },
                ),
                (
                    "item",
                    {
                        "question": "Can I switch between monthly and annual billing?",
                        "answer": (
                            "Yes, any time from your billing settings. Switching to annual "
                            "applies the 20% discount starting your next billing cycle."
                        ),
                    },
                ),
                (
                    "item",
                    {
                        "question": "What happens if I go over my recruiter seats?",
                        "answer": (
                            "We'll flag it in-app before you hit the limit. You can add seats "
                            "instantly on Starter and Growth; Enterprise plans are provisioned "
                            "with your success manager."
                        ),
                    },
                ),
                (
                    "item",
                    {
                        "question": "Do you offer discounts for startups or nonprofits?",
                        "answer": (
                            "Yes — agencies under 10 people and registered nonprofits get 30% "
                            "off Growth for the first year. Reach out to sales to get set up."
                        ),
                    },
                ),
            ],
        )
        home.add_child(instance=pricing)

        solutions = SolutionsPage(
            title="Solutions",
            slug="solutions",
            eyebrow="SOLUTIONS",
            heading="Everything your desk needs, connected.",
            subtitle=(
                "Start with the core CRM, then turn on the modules your agency actually "
                "needs — each one shares the same candidate and client record."
            ),
        )
        home.add_child(instance=solutions)

        use_cases = UseCasesPage(
            title="Use Cases",
            slug="use-cases",
            eyebrow="USE CASES",
            heading="Built for how your desk actually works.",
            subtitle=(
                "Four ways recruiting teams run their business on EvoHR — pick the shape "
                "that matches yours."
            ),
            cases=[
                (
                    "case",
                    {
                        "tag": "STAFFING AGENCIES",
                        "title": "High-volume desks that live and die by pipeline speed.",
                        "description": (
                            "Contract and temp desks moving dozens of candidates a week need "
                            "a pipeline that never drops a thread."
                        ),
                        "stat": "3.2×",
                        "stat_label": "faster time-to-fill",
                        "bullets": [
                            "Bulk requisition intake from client portals",
                            "Automated candidate-to-client matching",
                            "Contractor payroll on a weekly cycle",
                        ],
                    },
                ),
                (
                    "case",
                    {
                        "tag": "EXECUTIVE SEARCH",
                        "title": "Retained search built on relationships, not volume.",
                        "description": (
                            "Long cycles, high-touch client management, and confidential "
                            "searches need a CRM that tracks relationships over years, not weeks."
                        ),
                        "stat": "94%",
                        "stat_label": "client retention",
                        "bullets": [
                            "Confidential search workspaces per client",
                            "Long-cycle relationship & touchpoint tracking",
                            "Board-ready candidate presentations",
                        ],
                    },
                ),
                (
                    "case",
                    {
                        "tag": "RPO",
                        "title": "Embedded teams running a client's hiring at scale.",
                        "description": (
                            "Recruitment process outsourcing teams need client-branded "
                            "workflows that still roll up to one shared operations view."
                        ),
                        "stat": "68%",
                        "stat_label": "less admin time",
                        "bullets": [
                            "White-labeled client hiring portals",
                            "Cross-client reporting for RPO leadership",
                            "SLA and time-to-fill tracking per account",
                        ],
                    },
                ),
                (
                    "case",
                    {
                        "tag": "IN-HOUSE TALENT TEAMS",
                        "title": "Internal recruiting teams hiring for one company, not many.",
                        "description": (
                            "In-house teams trade the client layer for tighter integration "
                            "with HRIS, hiring managers, and offer approvals."
                        ),
                        "stat": "1",
                        "stat_label": "platform vs. 5 point tools",
                        "bullets": [
                            "Hiring manager collaboration & scorecards",
                            "Offer approval chains and e-signature",
                            "Direct handoff into onboarding",
                        ],
                    },
                ),
            ],
            shift_eyebrow="The shift",
            shift_title="What changes the week you switch on.",
            before_items=[
                ("item", t)
                for t in [
                    "Candidate data scattered across spreadsheets and inboxes",
                    "Client updates chased down through email threads",
                    "Timesheets and invoices reconciled by hand",
                    "Visa and compliance paperwork tracked ad hoc",
                ]
            ],
            after_items=[
                ("item", t)
                for t in [
                    "One shared CRM record for every candidate and client",
                    "Clients track requisitions live in their own portal",
                    "Payroll and invoicing generated automatically",
                    "Compliance checklists tracked per country, per placement",
                ]
            ],
        )
        home.add_child(instance=use_cases)

        who_we_serve = WhoWeServePage(
            title="Who We Serve",
            slug="who-we-serve",
            eyebrow="WHO WE SERVE",
            heading="One system, every seat on the team.",
            subtitle=(
                "Recruiters, ops, sales, and finance all work off the same record — just "
                "shaped around what each role actually needs."
            ),
            roles=[
                (
                    "role",
                    {
                        "tag": "AGENCY RECRUITERS",
                        "title": "Your pipeline, without the tab-switching.",
                        "description": (
                            "Source, screen, and submit candidates against live requisitions "
                            "— every note and status change logged against the same record "
                            "everyone else sees."
                        ),
                        "bullets": [
                            "One pipeline view across every open job order",
                            "Activity logged automatically as you work",
                            "Submit to client portals without leaving the record",
                        ],
                        "widget_type": "pipeline",
                        "widget_rows": [],
                        "widget_stages": [
                            {"label": "Sourced", "count": 12},
                            {"label": "Interview", "count": 6},
                            {"label": "Offer", "count": 2},
                            {"label": "Placed", "count": 3},
                        ],
                        "widget_skills": [],
                    },
                ),
                (
                    "role",
                    {
                        "tag": "RECRUITMENT OPS",
                        "title": "Oversight across every desk, in one place.",
                        "description": (
                            "See requisition health, desk load, and client SLAs across the "
                            "whole floor — without chasing individual recruiters for updates."
                        ),
                        "bullets": [
                            "Requisition status rolled up across all desks",
                            "SLA and time-to-fill tracking per client",
                            "Configurable pipeline stages per vertical",
                        ],
                        "widget_type": "hire",
                        "widget_rows": [
                            {"label": "Acme Corp · 4 roles", "status": "Reviewing", "tone": "amber"},
                            {"label": "Globex · 2 roles", "status": "Shortlisted", "tone": "primary"},
                            {"label": "Initech · 1 role", "status": "New", "tone": "neutral"},
                        ],
                        "widget_stages": [],
                        "widget_skills": [],
                    },
                ),
                (
                    "role",
                    {
                        "tag": "SALES & BD",
                        "title": "New logos and renewals, tracked like a real pipeline.",
                        "description": (
                            "Business development runs on the same system as delivery — so a "
                            "signed client flows straight into an active requisition."
                        ),
                        "bullets": [
                            "Deal pipeline separate from the delivery pipeline",
                            "Client health signals from delivery data",
                            "Signed deals convert to job orders instantly",
                        ],
                        "widget_type": "deals",
                        "widget_rows": [
                            {"label": "Acme Corp · renewal", "status": "Negotiating", "tone": "amber"},
                            {"label": "Northwind · new logo", "status": "Contract signed", "tone": "primary"},
                            {"label": "Initech · referral", "status": "Qualifying", "tone": "neutral"},
                        ],
                        "widget_stages": [],
                        "widget_skills": [],
                    },
                ),
                (
                    "role",
                    {
                        "tag": "FINANCE TEAMS",
                        "title": "Payroll and invoicing that reconciles itself.",
                        "description": (
                            "Contractor hours, placement fees, and client invoices flow from "
                            "the same source of truth delivery already updates daily."
                        ),
                        "bullets": [
                            "Payroll runs reconciled against logged hours",
                            "Placement invoices generated from won deals",
                            "Multi-currency payouts for global contractors",
                        ],
                        "widget_type": "payroll",
                        "widget_rows": [
                            {"label": "July payroll run", "status": "Reconciled", "tone": "primary"},
                            {"label": "Contractor batch #14", "status": "Needs review", "tone": "amber"},
                            {"label": "Bonus disbursement", "status": "Reconciled", "tone": "primary"},
                        ],
                        "widget_stages": [],
                        "widget_skills": [],
                    },
                ),
            ],
        )
        home.add_child(instance=who_we_serve)

        resources = ResourcesPage(
            title="Resources",
            slug="resources",
            eyebrow="RESOURCES",
            heading="Guides, playbooks, and help — all in one place.",
            subtitle="Everything to get your desk running on EvoHR, and keep it running well.",
            blog_posts=[
                ("item", {"title": t, "meta": m})
                for t, m in [
                    (
                        "Why time-to-fill is the wrong metric to optimize alone",
                        "Jul 12 · 6 min read",
                    ),
                    (
                        "A recruiter's guide to client portals that clients actually use",
                        "Jun 28 · 5 min read",
                    ),
                    ("Running contractor payroll across three countries", "Jun 14 · 8 min read"),
                ]
            ],
            guides=[
                ("item", {"title": t, "meta": m})
                for t, m in [
                    ("Switching from spreadsheets: a 2-week migration plan", "PDF · 14 pages"),
                    ("Building pipeline stages for a technical staffing desk", "PDF · 9 pages"),
                    ("Global mobility compliance checklist, by country", "PDF · 22 pages"),
                ]
            ],
            help_articles=[
                ("item", {"title": t, "meta": m})
                for t, m in [
                    ("How do I import candidates from a CSV?", "12.4k views"),
                    ("Setting up client portal branding", "8.1k views"),
                    ("Connecting payroll to your bank provider", "6.7k views"),
                ]
            ],
            api_docs_title="Build on the EvoHR API",
            api_docs_description="REST endpoints for candidates, requisitions, placements, and payroll.",
            api_docs_snippet=(
                'GET /v1/candidates/{id}\n'
                '{\n'
                '  "name": "Ava Thompson",\n'
                '  "stage": "interview",\n'
                '  "role": "Backend Engineer"\n'
                '}'
            ),
        )
        home.add_child(instance=resources)

        for data in PRODUCTS:
            data.setdefault("widget_rows", [])
            data.setdefault("widget_stages", [])
            data.setdefault("widget_skills", [])
            Product.objects.create(**data)

        settings = SiteSettings.for_site(site)
        settings.footer_tagline = "The recruitment CRM for agencies that place people for a living."
        settings.copyright_holder = "EvoHR, Inc. All rights reserved."
        settings.footer_columns = [
            (
                "column",
                {
                    "heading": "Solutions",
                    "url": "/solutions",
                    "links": ["Recruitment CRM", "Applicant Tracking", "Client Portal", "Reporting"],
                },
            ),
            (
                "column",
                {
                    "heading": "Use Cases",
                    "url": "/use-cases",
                    "links": [
                        "Staffing Agencies",
                        "Executive Search",
                        "RPO",
                        "In-house Talent Teams",
                    ],
                },
            ),
            (
                "column",
                {
                    "heading": "Who We Serve",
                    "url": "/who-we-serve",
                    "links": ["Agency Recruiters", "Recruitment Ops", "Sales & BD", "Finance Teams"],
                },
            ),
            (
                "column",
                {
                    "heading": "Resources",
                    "url": "/resources",
                    "links": ["Blog", "Guides", "Help Center", "API Docs"],
                },
            ),
        ]
        settings.cta_default_title = "Put your desk on the record."
        settings.cta_default_subtitle = (
            "Start a free 30-day trial. No credit card, no setup calls required."
        )
        settings.save()

        self.stdout.write(self.style.SUCCESS("CMS seeded: 6 pages, 6 products, site settings, site root updated."))
