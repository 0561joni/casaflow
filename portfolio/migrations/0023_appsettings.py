from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("portfolio", "0022_potential_deal_advanced_assumptions"),
    ]

    operations = [
        migrations.CreateModel(
            name="AppSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("effective_tax_rate", models.DecimalField(decimal_places=6, default=Decimal("0.000000"), max_digits=7)),
                ("tax_loss_benefit_enabled", models.BooleanField(default=True)),
            ],
            options={
                "verbose_name": "app settings",
                "verbose_name_plural": "app settings",
            },
        ),
    ]
