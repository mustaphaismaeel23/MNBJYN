from django.core.management.base import BaseCommand

from core.api import pu_import
from core.models import PollingUnit


class Command(BaseCommand):
    help = (
        "Create PLACEHOLDER polling units (8-15 per ward, no names, no voter counts) so the "
        "Situation Room and the app can be tested. Replace them with the official INEC list "
        "using import_polling_units. Safe to run repeatedly."
    )

    def handle(self, *args, **options):
        rows = pu_import.placeholder_rows()
        existing = PollingUnit.objects.count()
        result = pu_import.apply_rows(rows)
        self.stdout.write(self.style.SUCCESS(
            f"Placeholder polling units: {result['created']} created, {result['updated']} already existed "
            f"({existing} before, {PollingUnit.objects.count()} now)."
        ))
        self.stdout.write("Next: python manage.py import_polling_units <official.csv> --replace")
