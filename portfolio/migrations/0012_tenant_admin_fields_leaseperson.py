from django.db import migrations, models
import django.db.models.deletion


def create_primary_lease_people(apps, schema_editor):
    Lease = apps.get_model("portfolio", "Lease")
    LeasePerson = apps.get_model("portfolio", "LeasePerson")
    for lease in Lease.objects.select_related("tenant").all():
        LeasePerson.objects.get_or_create(
            lease=lease,
            person=lease.tenant,
            role="primary",
            defaults={
                "move_in_date": lease.start_date,
                "move_out_date": lease.end_date,
                "is_contract_signer": True,
                "notes": "",
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("portfolio", "0011_sync_lease_start_dates"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="birthday",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="tenant",
            name="relationship_notes",
            field=models.TextField(blank=True),
        ),
        migrations.CreateModel(
            name="LeasePerson",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("primary", "Primary contract tenant"),
                            ("co_tenant", "Co-contract tenant"),
                            ("occupant", "Occupant"),
                            ("child", "Child"),
                            ("other", "Other"),
                        ],
                        default="primary",
                        max_length=40,
                    ),
                ),
                ("move_in_date", models.DateField()),
                ("move_out_date", models.DateField(blank=True, null=True)),
                ("is_contract_signer", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True)),
                ("lease", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="people", to="portfolio.lease")),
                ("person", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="lease_links", to="portfolio.tenant")),
            ],
            options={
                "ordering": ["lease__unit__property__name", "lease__unit__label", "role", "person__last_name", "person__first_name"],
                "unique_together": {("lease", "person", "role")},
            },
        ),
        migrations.RunPython(create_primary_lease_people, migrations.RunPython.noop),
    ]
