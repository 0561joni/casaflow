from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("portfolio", "0018_remove_potentialfinancingscenario_loan_term_years"),
    ]

    operations = [
        migrations.AddField(
            model_name="property",
            name="object_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("apartment", "Apartment"),
                    ("single_family_house", "Single-family house"),
                    ("multi_family_house", "Multi-family house"),
                    ("mixed_use", "Mixed-use property"),
                    ("commercial", "Commercial property"),
                    ("land", "Land"),
                    ("other", "Other"),
                ],
                max_length=40,
            ),
        ),
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
                    ("bank_financing_pdf", "Bank Financing PDF"),
                    ("bank_financing_excel", "Bank Financing Excel"),
                    ("excel", "Excel"),
                    ("csv", "CSV"),
                    ("backup", "Backup"),
                ],
                max_length=40,
            ),
        ),
    ]
