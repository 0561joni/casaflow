from decimal import Decimal

from django.db import migrations, models


def backfill_monthly_payment(apps, schema_editor):
    AnnualLoanSnapshot = apps.get_model("portfolio", "AnnualLoanSnapshot")
    db_alias = schema_editor.connection.alias
    for snapshot in AnnualLoanSnapshot.objects.using(db_alias).all():
        if snapshot.debt_service:
            snapshot.monthly_payment = (snapshot.debt_service / Decimal("12")).quantize(Decimal("0.01"))
            snapshot.save(update_fields=["monthly_payment"])


class Migration(migrations.Migration):
    dependencies = [
        ("portfolio", "0002_property_recurring_expense"),
    ]

    operations = [
        migrations.AddField(
            model_name="annualloansnapshot",
            name="monthly_payment",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
        ),
        migrations.RunPython(backfill_monthly_payment, migrations.RunPython.noop),
    ]
