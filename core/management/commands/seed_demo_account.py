import os
from datetime import date

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from django.utils import timezone

from core.hr_views import get_or_create_hr_profile
from core.models import ActivityLog, Announcement, UserProfile
from payroll_benefits.models import (
    BankAccount,
    BenefitClaim,
    BenefitEnrollment,
    BenefitPlan,
    ComplianceEvent,
    PayrollRun,
    TaxProfile,
)
from people.models import (
    AttendanceRecord,
    Employee,
    LeaveRequest,
    PromotionRequest,
    Recognition,
    Shift,
    Survey,
    SurveyResponse,
)
from talent.models import Appraisal, CareerPath, CompetencyRating, Course, Enrollment, Goal, SuccessionPlan
from it_assets.models import Asset, AssetIncident, BYODCompliance, SupportTicket
from recruit.models import (
    BackgroundCheck,
    Candidate,
    Client,
    Offboarding,
    OffboardingTask,
    OfferLetter,
    Onboarding,
    OnboardingTask,
    Requisition,
)

User = get_user_model()

DEMO_USERNAME = 'demo'
YEAR = 2026


def d(month, day):
    return date(YEAR, month, day)


class Command(BaseCommand):
    help = (
        "Creates (or resets) the 'demo' account and fills it with the same sample "
        "candidates/clients/requisitions/payroll data the dashboard used to show as "
        "static mock data — so the public can log in as demo/<password> and see a "
        "populated desk, while every other signup starts with an empty one."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        password = os.getenv('DEMO_ACCOUNT_PASSWORD', 'PulseDemo2026!')

        def seed_role_account(username, role, *, first_name='', last_name='', employee=None, department=''):
            """Creates (or resets the password/profile on) a demo login for
            one of the newer roles — same idempotent get-or-create shape as
            the main 'demo' user, so re-running this command doesn't error
            on a second pass."""
            u, _ = User.objects.get_or_create(
                username=username,
                defaults={'email': f'{username}@Pulse.demo', 'first_name': first_name, 'last_name': last_name},
            )
            u.email = f'{username}@Pulse.demo'
            u.first_name = first_name
            u.last_name = last_name
            u.set_password(password)
            u.save()
            UserProfile.objects.update_or_create(
                user=u,
                defaults={'role': role, 'organization': org, 'employee': employee, 'department': department},
            )
            return u

        user, created = User.objects.get_or_create(
            username=DEMO_USERNAME,
            defaults={'email': 'demo@Pulse.app', 'first_name': 'Jordan', 'last_name': 'Blake'},
        )
        user.email = 'demo@Pulse.app'
        user.first_name = 'Jordan'
        user.last_name = 'Blake'
        user.set_password(password)
        user.save()
        org = get_or_create_hr_profile(user).organization

        # Idempotent: wipe this user's existing rows before reseeding so the
        # command can be re-run to reset the demo account to a clean
        # baseline (e.g. after visitors have poked at it for a while).
        Candidate.objects.filter(owner=user).delete()
        Requisition.objects.filter(owner=user).delete()
        Client.objects.filter(owner=user).delete()
        PayrollRun.objects.filter(owner=user).delete()
        ComplianceEvent.objects.filter(owner=user).delete()
        BenefitPlan.objects.filter(owner=user).delete()
        Asset.objects.filter(owner=user).delete()
        Employee.objects.filter(owner=user).delete()
        Survey.objects.filter(owner=user).delete()
        Course.objects.filter(owner=user).delete()
        ActivityLog.objects.filter(owner=user).delete()
        Announcement.objects.filter(owner=user).delete()

        clients = {
            'Northbridge Talent': Client.objects.create(
                owner=user, name='Northbridge Talent', industry='Technology', status='Active',
                contact_name='Wren Castillo', contact_email='wren@northbridge.demo',
            ),
            'Fernwood Staffing': Client.objects.create(
                owner=user, name='Fernwood Staffing', industry='Retail', status='Active',
                contact_name='Owen Faulkner', contact_email='owen@fernwood.demo',
            ),
            'Anchorpoint Search': Client.objects.create(
                owner=user, name='Anchorpoint Search', industry='Finance', status='Prospect',
                contact_name='Nadia Brooks', contact_email='nadia@anchorpoint.demo',
            ),
            'Duskline Partners': Client.objects.create(
                owner=user, name='Duskline Partners', industry='Healthcare', status='At risk',
                contact_name='Miles Sato', contact_email='miles@duskline.demo',
            ),
            'Cascade Recruiting': Client.objects.create(
                owner=user, name='Cascade Recruiting', industry='Manufacturing', status='Active',
                contact_name='Bea Larsen', contact_email='bea@cascade.demo',
            ),
            'Harborview Group': Client.objects.create(
                owner=user, name='Harborview Group', industry='Media', status='Prospect',
                contact_name='Theo Marsh', contact_email='theo@harborview.demo',
            ),
            'Meridian Staffing': Client.objects.create(
                owner=user, name='Meridian Staffing', industry='Finance', status='Active',
                contact_name='Priya Chandra', contact_email='priya@meridian.demo',
            ),
            'Silverline Talent': Client.objects.create(
                owner=user, name='Silverline Talent', industry='Technology', status='Active',
                contact_name='Jonah Pierce', contact_email='jonah@silverline.demo',
            ),
        }

        requisitions = {
            'Senior Backend Engineer': Requisition.objects.create(
                owner=user, client=clients['Northbridge Talent'], title='Senior Backend Engineer',
                recruiter='Jordan Blake', priority='High', status='Interviewing', posted_at=d(6, 28),
                requirements='5+ years building APIs in Python and Django, PostgreSQL, AWS, React, '
                             'REST APIs, and CI/CD pipelines.',
            ),
            'Field Sales Rep — West': Requisition.objects.create(
                owner=user, client=clients['Fernwood Staffing'], title='Field Sales Rep — West',
                recruiter='Ava Chen', priority='Medium', status='Interviewing', posted_at=d(7, 2),
            ),
            'DevOps Lead': Requisition.objects.create(
                owner=user, client=clients['Anchorpoint Search'], title='DevOps Lead',
                recruiter='Jordan Blake', priority='High', status='Offer stage', posted_at=d(6, 20),
                requirements='Kubernetes, Terraform, AWS, CI/CD pipelines, and monitoring/observability tooling.',
            ),
            'Product Designer': Requisition.objects.create(
                owner=user, client=clients['Harborview Group'], title='Product Designer',
                recruiter='Nate Osei', priority='Medium', status='Open', posted_at=d(7, 10),
            ),
            'Data Analyst': Requisition.objects.create(
                owner=user, client=clients['Meridian Staffing'], title='Data Analyst',
                recruiter='Ava Chen', priority='Low', status='Open', posted_at=d(7, 15),
            ),
            'Support Engineer': Requisition.objects.create(
                owner=user, client=clients['Duskline Partners'], title='Support Engineer',
                recruiter='Jordan Blake', priority='Low', status='On hold', posted_at=d(6, 15),
            ),
        }

        candidates = [
            dict(name='Ava Thompson', role='Senior Backend Engineer', client='Northbridge Talent',
                 requisition='Senior Backend Engineer', stage='Interview', source='LinkedIn', applied_at=d(7, 14),
                 email='ava.thompson@example.com', phone='+1 555-0142', current_salary=132000,
                 resume_text='Backend engineer with 6 years of experience building REST APIs in Python and '
                              'Django, deploying on AWS, and working with PostgreSQL. Hands-on React experience '
                              'building internal tooling. Comfortable owning CI/CD pipelines end to end.'),
            dict(name='Marcus Reed', role='Field Sales Rep — West', client='Fernwood Staffing',
                 requisition='Field Sales Rep — West', stage='Interview', source='Referral', applied_at=d(7, 12),
                 email='marcus.reed@example.com', phone='+1 555-0158', current_salary=68000),
            dict(name='Priya Nair', role='DevOps Lead', client='Anchorpoint Search',
                 requisition='DevOps Lead', stage='Offer', source='Job Board', applied_at=d(7, 9),
                 email='priya.nair@example.com', phone='+1 555-0173', current_salary=155000,
                 resume_text='DevOps lead with deep Kubernetes and Terraform experience across multi-account AWS '
                              'environments. Built CI/CD pipelines and observability/monitoring stacks for teams '
                              'of 40+ engineers.'),
            dict(name='Diego Alvarez', role='Support Engineer', client='Duskline Partners',
                 requisition='Support Engineer', stage='Rejected', source='LinkedIn', applied_at=d(7, 8),
                 email='diego.alvarez@example.com', phone='+1 555-0119'),
            dict(name='Lena Novak', role='People Ops Coordinator', client='Cascade Recruiting',
                 requisition=None, stage='Placed', source='Referral', applied_at=d(6, 30),
                 email='lena.novak@example.com', phone='+1 555-0187', placed_at=d(7, 13)),
            dict(name='Sam Okafor', role='Frontend Engineer', client='Northbridge Talent',
                 requisition=None, stage='Sourced', source='Sourced', applied_at=d(7, 16),
                 email='sam.okafor@example.com', phone='+1 555-0164'),
            dict(name='Ingrid Voss', role='Product Designer', client='Harborview Group',
                 requisition='Product Designer', stage='Interview', source='Job Board', applied_at=d(7, 11),
                 email='ingrid.voss@example.com', phone='+1 555-0135'),
            dict(name='Tariq Hassan', role='Data Analyst', client='Meridian Staffing',
                 requisition='Data Analyst', stage='Sourced', source='LinkedIn', applied_at=d(7, 15),
                 email='tariq.hassan@example.com', phone='+1 555-0128'),
            dict(name='Chloe Bennett', role='Account Executive', client='Fernwood Staffing',
                 requisition=None, stage='Offer', source='Referral', applied_at=d(7, 5),
                 email='chloe.bennett@example.com', phone='+1 555-0191'),
            dict(name='Ravi Thakur', role='QA Engineer', client='Silverline Talent',
                 requisition=None, stage='Placed', source='Job Board', applied_at=d(6, 22),
                 email='ravi.thakur@example.com', phone='+1 555-0146', placed_at=d(6, 29)),
        ]
        candidate_objs = {}
        for c in candidates:
            candidate_objs[c['name']] = Candidate.objects.create(
                owner=user,
                name=c['name'],
                role=c['role'],
                email=c.get('email', ''),
                phone=c.get('phone', ''),
                client=clients[c['client']],
                requisition=requisitions[c['requisition']] if c['requisition'] else None,
                stage=c['stage'],
                source=c['source'],
                current_salary=c.get('current_salary'),
                applied_at=c['applied_at'],
                placed_at=c.get('placed_at'),
                resume_text=c.get('resume_text', ''),
            )

        # A slice of the newer Acquisition/Onboarding/Offboarding sub-modules,
        # so the demo desk shows every Recruit feature populated, not just the
        # original candidates/clients/requisitions core.
        offer = OfferLetter.objects.create(
            owner=user, candidate=candidate_objs['Priya Nair'], job_title='DevOps Lead', salary='168000',
            start_date=d(8, 3),
            body='Dear Priya,\n\nWe are pleased to offer you the position of DevOps Lead at Anchorpoint Search, '
                 'starting August 3, 2026. We look forward to you joining the team.\n\nBest regards,\nHiring Team',
            status='Sent',
        )
        offer.sent_at = timezone.now()
        offer.save(update_fields=['sent_at'])

        check = BackgroundCheck.objects.create(
            owner=user, candidate=candidate_objs['Priya Nair'], check_type='Employment', status='In Progress',
            notes='Verifying last two employers.',
        )
        check.initiated_at = timezone.now()
        check.save(update_fields=['initiated_at'])

        onboarding = Onboarding.objects.create(
            owner=user, candidate=candidate_objs['Lena Novak'], start_date=d(7, 20), status='In Progress',
        )
        onboarding_tasks = [
            ('Pre-Joining Documents', 'Signed offer letter on file', 'Done'),
            ('Pre-Joining Documents', 'ID and work authorization verified', 'Done'),
            ('Orientation', 'Company orientation session scheduled', 'In Progress'),
            ('Training Plan', '30/60/90 training plan drafted', 'Pending'),
            ('Portal Access', 'HR and payroll portal accounts created', 'Done'),
            ('Device Assignment', 'Laptop and badge assigned', 'In Progress'),
        ]
        for category, title, status in onboarding_tasks:
            OnboardingTask.objects.create(onboarding=onboarding, category=category, title=title, status=status)

        offboarding = Offboarding.objects.create(
            owner=user, candidate=candidate_objs['Ravi Thakur'], last_working_day=d(7, 31),
            reason='Accepted an offer elsewhere', rehire_eligible=True, status='In Progress',
        )
        offboarding_tasks = [
            ('Documents Checklist', 'Exit interview completed', 'Done'),
            ('Documents Checklist', 'Final settlement paperwork signed', 'Pending'),
            ('Access Status', 'Email and SSO access revoked', 'Pending'),
            ('Hardware Clearance', 'Laptop and badge returned', 'Pending'),
        ]
        for category, title, status in offboarding_tasks:
            OffboardingTask.objects.create(offboarding=offboarding, category=category, title=title, status=status)

        payroll_runs = [
            ('July 2026, Run 2', 42, 186400, 'Reconciled'),
            ('July 2026, Run 1', 40, 178900, 'Reconciled'),
            ('Contractor batch #14', 6, 24300, 'Needs review'),
            ('June 2026, Run 2', 39, 171200, 'Reconciled'),
            ('Bonus disbursement — Q2', 18, 62750, 'Processing'),
        ]
        for period, contractors, amount, status in payroll_runs:
            PayrollRun.objects.create(
                owner=user, period=period, contractors=contractors, amount=amount, status=status,
            )
        flagged_run = PayrollRun.objects.filter(owner=user, status='Needs review').first()
        if flagged_run:
            flagged_run.discrepancy_flagged = True
            flagged_run.audit_notes = 'Contractor hours look 6 hours higher than last cycle — confirm with finance before release.'
            flagged_run.save(update_fields=['discrepancy_flagged', 'audit_notes'])

        # EVO-People Management demo data — a small org chart across two
        # departments, so Employee Database/Org Chart/the People dashboard
        # all show something real out of the box.
        cto = Employee.objects.create(
            owner=user, name='Marcus Webb', email='marcus.webb@Pulse.demo', job_title='CTO',
            department='Engineering', client_name='Northbridge Talent', salary_type='Salaried',
            location='Austin, TX', hire_date=d(1, 12), permanent_date=d(4, 12), status='Active', monthly_salary=18000,
        )
        eng_manager = Employee.objects.create(
            owner=user, name='Priya Chandran', email='priya.chandran@Pulse.demo', job_title='Engineering Manager',
            department='Engineering', client_name='Northbridge Talent', salary_type='Salaried',
            location='Austin, TX', manager=cto, hire_date=d(3, 4), permanent_date=d(6, 4), status='Active', monthly_salary=12500,
        )
        diego = Employee.objects.create(
            owner=user, name='Diego Fernandez', email='diego.fernandez@Pulse.demo', job_title='Senior Engineer',
            department='Engineering', client_name='Northbridge Talent', salary_type='Salaried',
            location='Remote — Mexico City', manager=eng_manager, hire_date=d(4, 18), permanent_date=d(7, 18), status='Active', monthly_salary=9800,
        )
        sofia = Employee.objects.create(
            owner=user, name='Sofia Marin', email='sofia.marin@Pulse.demo', job_title='Engineer',
            department='Engineering', client_name='Northbridge Talent', salary_type='Salaried',
            location='Remote — Barcelona', manager=eng_manager, hire_date=d(6, 2), status='On Leave', monthly_salary=7200,
        )
        hr_lead = Employee.objects.create(
            owner=user, name='Jordan Ellis', email='jordan.ellis@Pulse.demo', job_title='Head of People',
            department='People Ops', salary_type='Salaried', location='Austin, TX',
            hire_date=d(2, 9), permanent_date=d(5, 9), status='Active', monthly_salary=10500,
        )
        tasha = Employee.objects.create(
            owner=user, name='Tasha Reyes', email='tasha.reyes@Pulse.demo', job_title='HR Coordinator',
            department='People Ops', salary_type='Hourly', location='Austin, TX',
            manager=hr_lead, hire_date=d(5, 20), status='Active', monthly_salary=5400,
        )
        # Contractor role login (below) needs a real Employee row to link
        # to — UserProfile.clean() requires employee_id for role='Contractor'
        # — so this one uses salary_type='Contract' rather than being just
        # another salaried hire.
        contractor_employee = Employee.objects.create(
            owner=user, name='Contractor Demo', email='demo_contractor@Pulse.demo', job_title='Contract Engineer',
            department='Engineering', client_name='Northbridge Talent', salary_type='Contract',
            location='Remote — Lisbon', manager=eng_manager, hire_date=d(6, 15), status='Active', monthly_salary=6800,
        )

        # Demo logins for the newer roles (IT Manager/Finance Admin are
        # normally Admin/superuser-provisioned via Django admin, not this
        # HR-owned flow, but seeding them here directly gives the demo org a
        # working login for every role without needing a separate manual
        # step). Same password as the main 'demo' account.
        seed_role_account('demo_dept_head', 'Department Head', first_name='Priya', last_name='Chandran (Dept Head)',
                           employee=eng_manager, department='Engineering')
        seed_role_account('demo_recruiter', 'Recruiter', first_name='Recruiter', last_name='Demo')
        seed_role_account('demo_it_manager', 'IT Manager', first_name='IT', last_name='Manager Demo')
        seed_role_account('demo_finance_admin', 'Finance Admin', first_name='Finance', last_name='Admin Demo')
        seed_role_account('demo_auditor', 'Auditor', first_name='Auditor', last_name='Demo')
        seed_role_account('demo_contractor', 'Contractor', first_name='Contractor', last_name='Demo',
                           employee=contractor_employee)

        # Attendance Management
        AttendanceRecord.objects.create(
            owner=user, employee=diego, date=d(7, 24), clock_in='09:02', clock_out='18:15', overtime_hours=1.25,
        )
        AttendanceRecord.objects.create(
            owner=user, employee=tasha, date=d(7, 24), clock_in='08:55', clock_out='17:30',
        )
        AttendanceRecord.objects.create(
            owner=user, employee=diego, date=d(7, 30), clock_in='09:05', clock_out=None,
        )
        AttendanceRecord.objects.create(
            owner=user, employee=tasha, date=d(7, 30), clock_in='08:48', clock_out=None,
        )
        AttendanceRecord.objects.create(
            owner=user, employee=eng_manager, date=d(7, 30), clock_in='08:57', clock_out=None,
        )

        # Shift Scheduling per Department — a working week (Mon–Fri, 7/27–7/31)
        # per employee, so the People dashboard's schedule views have a real
        # weekly pattern to group and display rather than a single one-off shift.
        for wk_date, notes in [
            (d(7, 27), ''), (d(7, 28), 'On-call for the Engineering deploy window.'),
            (d(7, 29), ''), (d(7, 30), ''), (d(7, 31), ''),
        ]:
            Shift.objects.create(owner=user, employee=diego, date=wk_date, start_time='09:00', end_time='17:30', notes=notes)
        for wk_date in [d(7, 27), d(7, 28), d(7, 29), d(7, 30), d(7, 31)]:
            Shift.objects.create(owner=user, employee=eng_manager, date=wk_date, start_time='09:00', end_time='17:00')
            Shift.objects.create(owner=user, employee=hr_lead, date=wk_date, start_time='08:30', end_time='16:30')
            Shift.objects.create(owner=user, employee=tasha, date=wk_date, start_time='08:30', end_time='17:00')
        for wk_date in [d(7, 27), d(7, 29), d(7, 31)]:
            Shift.objects.create(owner=user, employee=sofia, date=wk_date, start_time='10:00', end_time='15:00')
        LeaveRequest.objects.create(
            owner=user, employee=sofia, leave_type='Sick', start_date=d(7, 22), end_date=d(7, 29),
            hours=48, status='Approved', reason='Recovering from minor surgery.',
        )
        LeaveRequest.objects.create(
            owner=user, employee=tasha, leave_type='Vacation', start_date=d(8, 10), end_date=d(8, 14),
            hours=40, status='Pending', reason='Family trip.',
        )

        # Employee Engagement
        pulse = Survey.objects.create(
            owner=user, kind='Pulse Check', title='How was your week?',
            questions=[
                'On a scale of 1–5, how manageable was your workload this week?',
                'Do you feel supported by your manager right now?',
                'Is there anything blocking your progress this week?',
            ],
            frequency='Bi-yearly', is_open=True,
        )
        SurveyResponse.objects.create(survey=pulse, employee=diego, rating=4, response_text='Busy but good.')
        SurveyResponse.objects.create(survey=pulse, employee=eng_manager, rating=3, response_text='A bit stretched with the release.')
        Recognition.objects.create(
            owner=user, employee=diego, recognition_type='Above & Beyond', given_by='Priya Chandran',
            message='Shipped the auth migration a full week ahead of schedule — great work under pressure.',
        )
        PromotionRequest.objects.create(
            owner=user, employee=diego, from_title='Senior Engineer', to_title='Staff Engineer',
            from_department='Engineering', to_department='Engineering', effective_date=d(9, 1),
            status='Pending', notes='Ready for a staff-level scope based on Q2/Q3 impact.',
        )

        # EVO-Talent Management demo data
        Goal.objects.create(
            owner=user, employee=diego, title='Ship the auth migration', target_date=d(8, 1),
            status='In Progress', progress=80,
        )
        Goal.objects.create(
            owner=user, employee=tasha, title='Complete HR compliance certification', target_date=d(9, 15),
            status='Not Started', progress=0,
        )
        Appraisal.objects.create(
            owner=user, employee=diego, period='2026 Mid-Year Review', reviewer='Priya Chandran',
            overall_rating=4, strengths='Strong technical execution, mentors juniors well.',
            areas_for_improvement='Could delegate more during crunch periods.', status='Finalized',
        )
        CompetencyRating.objects.create(owner=user, employee=diego, competency='System Design', level=4)
        CompetencyRating.objects.create(owner=user, employee=diego, competency='Mentorship', level=3)
        CompetencyRating.objects.create(owner=user, employee=tasha, competency='Employment Law', level=3)
        course = Course.objects.create(
            owner=user, title='Leadership Fundamentals', description='An intro course on managing people.',
            duration_hours=6,
        )
        Enrollment.objects.create(course=course, employee=eng_manager, status='Completed', completed_at=d(6, 30))
        Enrollment.objects.create(course=course, employee=diego, status='In Progress')
        CareerPath.objects.create(
            owner=user, employee=diego, current_role='Senior Engineer', target_role='Staff Engineer',
            department='Engineering', target_date=d(12, 1),
            milestones='Lead a cross-team project; mentor two engineers; present at an internal tech talk.',
        )
        SuccessionPlan.objects.create(
            owner=user, employee=eng_manager, potential_rating='High', performance_rating='High',
            successor_notes='Strong candidate for Director of Engineering within 12–18 months.', ready_now=False,
        )
        SuccessionPlan.objects.create(
            owner=user, employee=diego, potential_rating='High', performance_rating='Medium',
            successor_notes='On track for Engineering Manager once staff-level scope is proven.', ready_now=False,
        )

        # EVO-Payroll & Benefits demo data — Tax Compliance, Compliance
        # Calendar, Direct Deposit, and Benefits (enrollment/claims), so
        # every sub-module has something real to show.
        TaxProfile.objects.create(
            owner=user, employee=diego, country='United States', tax_id='XXX-XX-4821',
            filing_status='Single', compliance_status='Compliant', last_reviewed=d(6, 1),
        )
        TaxProfile.objects.create(
            owner=user, employee=sofia, country='Portugal', tax_id='PT-778213456',
            filing_status='Single', compliance_status='Action Required',
            notes='NHR status renewal paperwork still outstanding.', last_reviewed=d(4, 15),
        )
        TaxProfile.objects.create(
            owner=user, employee=hr_lead, country='United States', tax_id='XXX-XX-9012',
            filing_status='Married', compliance_status='Compliant', last_reviewed=d(6, 1),
        )

        ComplianceEvent.objects.create(
            owner=user, country='United States', title='Q3 941 payroll tax filing',
            category='Tax Filing', due_date=d(10, 31),
        )
        ComplianceEvent.objects.create(
            owner=user, country='Portugal', title='NHR status renewal deadline',
            category='Regulatory', due_date=d(8, 5),
            notes='Blocks Sofia Marin\'s continued reduced-rate withholding if missed.',
        )
        ComplianceEvent.objects.create(
            owner=user, country='United States', title='EUR/USD payroll FX rate lock for August run',
            category='Currency Update', due_date=d(7, 30),
        )
        ComplianceEvent.objects.create(
            owner=user, country='United States', title='Q2 941 payroll tax filing',
            category='Tax Filing', due_date=d(7, 15), completed=True,
        )

        BankAccount.objects.create(
            owner=user, employee=diego, bank_name='First Horizon Bank', account_holder_name='Diego Fernandez',
            account_number_last4='8847', routing_number='084000026', account_type='Checking',
            is_primary=True, verified=True,
        )
        BankAccount.objects.create(
            owner=user, employee=tasha, bank_name='Ally Bank', account_holder_name='Tasha Reyes',
            account_number_last4='9934', routing_number='124003116', account_type='Savings',
            is_primary=True, verified=False,
        )

        health_plan = BenefitPlan.objects.create(
            owner=user, name='Pulse Gold PPO', plan_type='Health', provider='Blue Shield',
            employee_cost=85, employer_cost=410,
            description='Preferred provider organization plan covering medical, with a low deductible.',
        )
        dental_plan = BenefitPlan.objects.create(
            owner=user, name='Bright Smile Dental', plan_type='Dental', provider='Delta Dental',
            employee_cost=12, employer_cost=38,
        )
        retirement_plan = BenefitPlan.objects.create(
            owner=user, name='401(k) — 4% match', plan_type='Retirement', provider='Fidelity',
            employee_cost=0, employer_cost=0,
            description='Employer matches up to 4% of salary on employee contributions.',
        )
        BenefitEnrollment.objects.create(
            owner=user, employee=diego, plan=health_plan, coverage_level='Employee + Spouse',
            status='Enrolled', enrolled_at=d(1, 15),
        )
        BenefitEnrollment.objects.create(
            owner=user, employee=diego, plan=retirement_plan, coverage_level='Employee Only',
            status='Enrolled', enrolled_at=d(1, 15),
        )
        BenefitEnrollment.objects.create(
            owner=user, employee=tasha, plan=health_plan, coverage_level='Employee Only',
            status='Enrolled', enrolled_at=d(5, 20),
        )
        BenefitEnrollment.objects.create(
            owner=user, employee=sofia, plan=dental_plan, coverage_level='Employee Only',
            status='Pending',
        )
        BenefitClaim.objects.create(
            owner=user, employee=diego, plan=health_plan, claim_type='Specialist visit copay',
            amount=45, status='Under Review', description='Dermatology follow-up.',
        )
        BenefitClaim.objects.create(
            owner=user, employee=tasha, plan=dental_plan, claim_type='Routine cleaning',
            amount=0, status='Paid',
        )

        # EVO-IT & Asset Management demo data — Asset Inventory, Device
        # Provisioning (assigned_to), Warranty Tracking, IT Support
        # Requests, Device Tracker, and BYOD Security Policy.
        laptop_diego = Asset.objects.create(
            owner=user, asset_tag='PLS-LT-1042', name='MacBook Pro 14"', category='Laptop',
            serial_number='C02FX3QJMD6T', purchase_date=d(4, 15), warranty_expiry=date(YEAR + 1, 4, 15),
            status='Assigned', assigned_to=diego, assigned_at=d(4, 18),
        )
        laptop_tasha = Asset.objects.create(
            owner=user, asset_tag='PLS-LT-1055', name='Dell XPS 13', category='Laptop',
            serial_number='5CD1234XYZ', purchase_date=d(5, 18), warranty_expiry=date(YEAR, 8, 1),
            status='Assigned', assigned_to=tasha, assigned_at=d(5, 20),
        )
        monitor_spare = Asset.objects.create(
            owner=user, asset_tag='PLS-MN-2011', name='Dell UltraSharp 27"', category='Monitor',
            serial_number='CN-0T7C9P', purchase_date=d(2, 1), warranty_expiry=date(YEAR + 2, 2, 1),
            status='In Stock',
        )
        phone_sofia = Asset.objects.create(
            owner=user, asset_tag='PLS-PH-3007', name='iPhone 15', category='Phone',
            serial_number='F2LN8Q3RJ9', purchase_date=d(6, 2), warranty_expiry=date(YEAR, 12, 2),
            status='Assigned', assigned_to=sofia, assigned_at=d(6, 2), is_byod=False,
        )
        personal_laptop_eng_manager = Asset.objects.create(
            owner=user, asset_tag='PLS-BYOD-004', name="Priya's personal MacBook Air", category='Laptop',
            serial_number='FVFXQ2K1Q6L4', status='Assigned', assigned_to=eng_manager, assigned_at=d(3, 4),
            is_byod=True, notes='Personal device approved for email + Slack access only.',
        )

        SupportTicket.objects.create(
            owner=user, asset=laptop_tasha, employee=tasha, subject='Laptop battery draining fast',
            description='Battery drops from 100% to 40% within two hours of light use.',
            category='Repair Request', priority='Medium', status='In Progress',
        )
        SupportTicket.objects.create(
            owner=user, asset=None, employee=diego, subject='Need a second monitor',
            description='Requesting a second monitor for the new desk setup.',
            category='Device Query', priority='Low', status='Open',
        )
        resolved_ticket = SupportTicket.objects.create(
            owner=user, asset=phone_sofia, employee=sofia, subject='Set up company email on new phone',
            description='Needed IT to configure MDM profile on the new phone.',
            category='Device Query', priority='Low', status='Resolved',
        )
        resolved_ticket.resolved_at = timezone.now()
        resolved_ticket.save(update_fields=['resolved_at'])

        AssetIncident.objects.create(
            owner=user, asset=laptop_diego, employee=diego, incident_type='Damage',
            description='Small crack on the top-left corner of the lid from a drop.',
            incident_date=d(6, 10), resolved=True,
            resolution_notes='Cosmetic only — no functional impact, no repair needed.', cost=0,
        )
        AssetIncident.objects.create(
            owner=user, asset=laptop_tasha, employee=tasha, incident_type='Repair',
            description='Battery replacement, related to the open support ticket.',
            incident_date=d(7, 20), resolved=False, cost=89,
        )

        BYODCompliance.objects.create(
            owner=user, asset=personal_laptop_eng_manager, employee=eng_manager,
            encryption_enabled=True, antivirus_installed=True, passcode_enabled=True,
            compliance_status='Compliant', last_checked=d(6, 1),
        )

        activity_items = [
            ('Ava Thompson advanced to Interview for Senior Backend Engineer', 'primary'),
            ('Offer sent to Priya Nair for DevOps Lead', 'primary'),
            ('New requisition opened: Data Analyst at Meridian Staffing', 'neutral'),
            ('Diego Alvarez marked not a fit for Support Engineer', 'maroon'),
            ('Contractor batch #14 payroll needs review', 'amber'),
            ('Lena Novak placed as People Ops Coordinator', 'primary'),
        ]
        # Oldest first, so `created_at` ordering (newest-first) puts them back
        # in the same order the original static list displayed them in.
        for message, tone in reversed(activity_items):
            ActivityLog.objects.create(owner=user, message=message, tone=tone)

        announcements = [
            'All-hands meeting Friday at 4 PM ET — Q3 company update from Marcus.',
            'Reminder: Q3 performance reviews are due by August 15.',
        ]
        for message in reversed(announcements):
            Announcement.objects.create(owner=user, message=message)

        self.stdout.write(self.style.SUCCESS(
            f"{'Created' if created else 'Reset'} demo account: username={DEMO_USERNAME!r} password={password!r}"
        ))
        role_usernames = [
            'demo_dept_head', 'demo_recruiter', 'demo_it_manager', 'demo_finance_admin',
            'demo_auditor', 'demo_contractor',
        ]
        self.stdout.write(self.style.SUCCESS(
            f"Role demo logins (same password): {', '.join(role_usernames)}"
        ))
