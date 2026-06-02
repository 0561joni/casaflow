from django.db import migrations, models


def dedupe_report_exports(apps, schema_editor):
    ReportExport = apps.get_model("portfolio", "ReportExport")
    seen = set()
    for export in ReportExport.objects.order_by("-created_at", "-id"):
        key = (export.export_type, export.file_name)
        if key in seen:
            export.delete()
        else:
            seen.add(key)


class Migration(migrations.Migration):
    dependencies = [
        ("portfolio", "0020_consistency_cleanup"),
    ]

    operations = [
        migrations.RunPython(dedupe_report_exports, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="reportexport",
            constraint=models.UniqueConstraint(fields=("export_type", "file_name"), name="unique_export_type_file_name"),
        ),
    ]
