from django.core.management.base import BaseCommand

from core.api.services import security_warnings


class Command(BaseCommand):
    help = "Go-live checklist: lists everything to fix before real results are collected."

    def handle(self, *args, **options):
        items = security_warnings()
        if not items:
            self.stdout.write(self.style.SUCCESS("All checks passed. Ready to go live."))
            return
        for w in items:
            style = self.style.ERROR if w["level"] == "critical" else self.style.WARNING
            self.stdout.write(style(f"[{w['level'].upper()}] {w['message']}"))
