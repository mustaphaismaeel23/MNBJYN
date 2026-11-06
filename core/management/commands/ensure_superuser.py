from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

from core.accounts import ensure_superuser


class Command(BaseCommand):
    help = "Create (or repair) the MNBJYN super-user. Safe to run repeatedly."

    def handle(self, *args, **options):
        try:
            user, created = ensure_superuser()
        except ImproperlyConfigured as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(
            f"Super-user '{user.username}' {'created' if created else 'updated'}."
        ))
