from django.db import migrations, models


REMOVED_EXPORT_TYPES = [
    "portfolio_pdf",
    "property_pdf",
    "loan_pdf",
    "rent_income_pdf",
    "rent_income_excel",
    "excel",
    "csv",
]


def remove_legacy_export_rows(apps, schema_editor):
    ReportExport = apps.get_model("portfolio", "ReportExport")
    ReportExport.objects.filter(export_type__in=REMOVED_EXPORT_TYPES).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("portfolio", "0019_property_object_type_bank_export_types"),
    ]

    operations = [
        migrations.RenameField(
            model_name="potentialfinancingscenario",
            old_name="personal_cash_out",
            new_name="owner_cash_out",
        ),
        migrations.RunPython(remove_legacy_export_rows, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="reportexport",
            name="export_type",
            field=models.CharField(
                choices=[
                    ("bank_financing_pdf", "Bank Financing PDF"),
                    ("bank_financing_excel", "Bank Financing Excel"),
                    ("backup", "Backup"),
                ],
                max_length=40,
            ),
        ),
    ]
