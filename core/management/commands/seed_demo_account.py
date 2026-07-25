import os
from datetime import date

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import ActivityLog
from payroll_benefits.models import PayrollRun
from recruit.models import Candidate, Client, Requisition

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
        password = os.getenv('DEMO_ACCOUNT_PASSWORD', 'EvoHRDemo2026!')

        user, created = User.objects.get_or_create(
            username=DEMO_USERNAME,
            defaults={'email': 'demo@evohr.app', 'first_name': 'Jordan', 'last_name': 'Blake'},
        )
        user.email = 'demo@evohr.app'
        user.first_name = 'Jordan'
        user.last_name = 'Blake'
        user.set_password(password)
        user.save()

        # Idempotent: wipe this user's existing rows before reseeding so the
        # command can be re-run to reset the demo account to a clean
        # baseline (e.g. after visitors have poked at it for a while).
        Candidate.objects.filter(owner=user).delete()
        Requisition.objects.filter(owner=user).delete()
        Client.objects.filter(owner=user).delete()
        PayrollRun.objects.filter(owner=user).delete()
        ActivityLog.objects.filter(owner=user).delete()

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
            ),
            'Field Sales Rep — West': Requisition.objects.create(
                owner=user, client=clients['Fernwood Staffing'], title='Field Sales Rep — West',
                recruiter='Ava Chen', priority='Medium', status='Interviewing', posted_at=d(7, 2),
            ),
            'DevOps Lead': Requisition.objects.create(
                owner=user, client=clients['Anchorpoint Search'], title='DevOps Lead',
                recruiter='Jordan Blake', priority='High', status='Offer stage', posted_at=d(6, 20),
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
                 requisition='Senior Backend Engineer', stage='Interview', source='LinkedIn', applied_at=d(7, 14)),
            dict(name='Marcus Reed', role='Field Sales Rep — West', client='Fernwood Staffing',
                 requisition='Field Sales Rep — West', stage='Interview', source='Referral', applied_at=d(7, 12)),
            dict(name='Priya Nair', role='DevOps Lead', client='Anchorpoint Search',
                 requisition='DevOps Lead', stage='Offer', source='Job Board', applied_at=d(7, 9)),
            dict(name='Diego Alvarez', role='Support Engineer', client='Duskline Partners',
                 requisition='Support Engineer', stage='Rejected', source='LinkedIn', applied_at=d(7, 8)),
            dict(name='Lena Novak', role='People Ops Coordinator', client='Cascade Recruiting',
                 requisition=None, stage='Placed', source='Referral', applied_at=d(6, 30)),
            dict(name='Sam Okafor', role='Frontend Engineer', client='Northbridge Talent',
                 requisition=None, stage='Sourced', source='Sourced', applied_at=d(7, 16)),
            dict(name='Ingrid Voss', role='Product Designer', client='Harborview Group',
                 requisition='Product Designer', stage='Interview', source='Job Board', applied_at=d(7, 11)),
            dict(name='Tariq Hassan', role='Data Analyst', client='Meridian Staffing',
                 requisition='Data Analyst', stage='Sourced', source='LinkedIn', applied_at=d(7, 15)),
            dict(name='Chloe Bennett', role='Account Executive', client='Fernwood Staffing',
                 requisition=None, stage='Offer', source='Referral', applied_at=d(7, 5)),
            dict(name='Ravi Thakur', role='QA Engineer', client='Silverline Talent',
                 requisition=None, stage='Placed', source='Job Board', applied_at=d(6, 22)),
        ]
        for c in candidates:
            Candidate.objects.create(
                owner=user,
                name=c['name'],
                role=c['role'],
                client=clients[c['client']],
                requisition=requisitions[c['requisition']] if c['requisition'] else None,
                stage=c['stage'],
                source=c['source'],
                applied_at=c['applied_at'],
            )

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

        self.stdout.write(self.style.SUCCESS(
            f"{'Created' if created else 'Reset'} demo account: username={DEMO_USERNAME!r} password={password!r}"
        ))
