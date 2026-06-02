from django.db import migrations
from django.db.models import Min


def sync_lease_start_dates(apps, schema_editor):
    Lease = apps.get_model("portfolio", "Lease")
    leases = Lease.objects.annotate(earliest_rent_start=Min("rent_periods__effective_start")).filter(earliest_rent_start__isnull=False)
    for lease in leases:
        if lease.start_date != lease.earliest_rent_start:
            lease.start_date = lease.earliest_rent_start
            lease.save(update_fields=["start_date"])


class Migration(migrations.Migration):

    dependencies = [
        ("portfolio", "0010_alter_reportexport_export_type"),
    ]

    operations = [
        migrations.RunPython(sync_lease_start_dates, migrations.RunPython.noop),
    ]
