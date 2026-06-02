from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("portfolio", "0024_portfolio_tax_settings"),
    ]

    operations = [
        migrations.AddField(
            model_name="appsettings",
            name="landlord_city",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="appsettings",
            name="landlord_email",
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name="appsettings",
            name="landlord_fax",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="appsettings",
            name="landlord_name",
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name="appsettings",
            name="landlord_phone",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="appsettings",
            name="landlord_street",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="appsettings",
            name="landlord_zip",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AlterField(
            model_name="reportexport",
            name="export_type",
            field=models.CharField(
                choices=[
                    ("bank_financing_pdf", "Bank Financing PDF"),
                    ("bank_financing_excel", "Bank Financing Excel"),
                    ("mietbescheinigung_pdf", "Mietbescheinigung PDF"),
                    ("backup", "Backup"),
                ],
                max_length=40,
            ),
        ),
    ]
