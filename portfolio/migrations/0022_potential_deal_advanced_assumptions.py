from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("portfolio", "0021_dedupe_report_exports"),
    ]

    operations = [
        migrations.AddField(
            model_name="potentialdeal",
            name="buying_costs",
            field=models.DecimalField(blank=True, decimal_places=2, default=Decimal("0.00"), max_digits=12),
        ),
        migrations.AddField(
            model_name="potentialdeal",
            name="minimum_dscr",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True),
        ),
        migrations.AddField(
            model_name="potentialdeal",
            name="maximum_ltv",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=7, null=True),
        ),
    ]
