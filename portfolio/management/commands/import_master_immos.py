from datetime import date

from django.core.management.base import BaseCommand, CommandError

from portfolio.importer import import_master_immos


class Command(BaseCommand):
    help = "Import a Master-Immos workbook into the database."

    def add_arguments(self, parser):
        parser.add_argument("workbook")
        parser.add_argument("--year", type=int, default=date.today().year)

    def handle(self, *args, **options):
        try:
            run = import_master_immos(options["workbook"], options["year"])
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"Imported {run.source_name} with {len(run.warnings)} warning(s)."))
        for warning in run.warnings:
            self.stdout.write(self.style.WARNING(warning))
