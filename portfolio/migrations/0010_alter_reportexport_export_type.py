from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("portfolio", "0009_contact_propertyadministration_unitadministration_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="reportexport",
            name="export_type",
            field=models.CharField(
                choices=[
                    ("portfolio_pdf", "Portfolio PDF"),
                    ("property_pdf", "Property PDF"),
                    ("loan_pdf", "Loan PDF"),
                    ("rent_income_pdf", "Rent Income PDF"),
                    ("rent_income_excel", "Rent Income Excel"),
                    ("excel", "Excel"),
                    ("csv", "CSV"),
                    ("backup", "Backup"),
                ],
                max_length=40,
            ),
        ),
    ]
