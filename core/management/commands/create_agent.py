from django.core.management.base import BaseCommand, CommandError

from core.api import validators as v
from core.lga_data import LGA_INDEX
from core.models import ResultAgent


class Command(BaseCommand):
    help = "Create a results-app user. Use --role admin to create the first results administrator."

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True)
        parser.add_argument("--phone", required=True)
        parser.add_argument("--role", choices=[r for r, _ in ResultAgent.Role.choices], default="agent")
        parser.add_argument("--lga", default="", help="Supervisors: LGA key to limit them to (e.g. kano_municipal).")

    def handle(self, *args, **o):
        phone = v.normalise_phone(o["phone"])
        if not v.phone_is_valid(phone):
            raise CommandError("Invalid phone number.")
        if o["lga"] and o["lga"] not in LGA_INDEX:
            raise CommandError("Unknown LGA key.")
        if ResultAgent.objects.filter(phone=phone).exists():
            raise CommandError("An agent with this phone number already exists.")
        pin = v.generate_pin()
        agent = ResultAgent(full_name=o["name"], phone=phone, role=o["role"], lga_scope=o["lga"], must_change_pin=True)
        agent.set_pin(pin)
        agent.save()
        self.stdout.write(self.style.SUCCESS(f"Created {agent} (id {agent.pk})."))
        self.stdout.write(f"Temporary PIN (shown once, must be changed at first login): {pin}")
