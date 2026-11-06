from django.core.management.base import BaseCommand, CommandError

from core.api import pu_import


class Command(BaseCommand):
    help = "Import the official polling-unit list from a CSV file (see docs/API.md for the columns)."

    def add_arguments(self, parser):
        parser.add_argument("csv_file")
        parser.add_argument(
            "--replace", action="store_true",
            help="Remove placeholder/old polling units in the wards found in the file that are not listed "
                 "(units that already have results are deactivated instead of deleted).",
        )
        parser.add_argument("--dry-run", action="store_true", help="Check the file only; write nothing.")

    def handle(self, *args, **opts):
        try:
            with open(opts["csv_file"], "rb") as fh:
                raw = fh.read()
        except OSError as exc:
            raise CommandError(str(exc))
        rows, errors = pu_import.parse_csv(pu_import.decode_bytes(raw))
        for line in errors:
            self.stderr.write(line)
        if errors:
            raise CommandError(f"{len(errors)} problem(s) found (first 50 shown). Nothing was imported.")
        self.stdout.write(f"{len(rows)} valid rows.")
        if opts["dry_run"]:
            return
        result = pu_import.apply_rows(rows, replace=opts["replace"])
        self.stdout.write(self.style.SUCCESS(
            "Imported: {created} created, {updated} updated, {removed} removed, {deactivated} deactivated.".format(**result)
        ))
