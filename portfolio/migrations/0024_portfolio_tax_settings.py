from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("portfolio", "0023_appsettings"),
    ]

    operations = [
        migrations.AddField(
            model_name="appsettings",
            name="tax_calculations_enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.CreateModel(
            name="AnnualPortfolioTax",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("year", models.PositiveIntegerField(unique=True)),
                ("tax_deductible_costs", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("notes", models.TextField(blank=True)),
            ],
            options={
                "verbose_name": "annual portfolio tax",
                "verbose_name_plural": "annual portfolio taxes",
                "ordering": ["-year"],
            },
        ),
    ]
