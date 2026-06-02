from decimal import Decimal

from django.db import migrations, models
from django.db.models import Sum


def backfill_owner_cash_out(apps, schema_editor):
    Property = apps.get_model("portfolio", "Property")
    Loan = apps.get_model("portfolio", "Loan")
    db_alias = schema_editor.connection.alias
    for property_obj in Property.objects.using(db_alias).all():
        owner_purchase_price = property_obj.purchase_price * property_obj.ownership_share
        owner_purchase_costs = property_obj.purchase_costs * property_obj.ownership_share
        original_debt = (
            Loan.objects.using(db_alias)
            .filter(property=property_obj)
            .aggregate(total=Sum("original_amount"))["total"]
            or Decimal("0.00")
        )
        property_obj.owner_cash_down_payment = max(Decimal("0.00"), owner_purchase_price - original_debt).quantize(Decimal("0.01"))
        property_obj.owner_cash_purchase_costs = owner_purchase_costs.quantize(Decimal("0.01"))
        property_obj.save(update_fields=["owner_cash_down_payment", "owner_cash_purchase_costs"])


class Migration(migrations.Migration):
    dependencies = [
        ("portfolio", "0003_annualloansnapshot_monthly_payment"),
    ]

    operations = [
        migrations.AddField(
            model_name="property",
            name="owner_cash_down_payment",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
        ),
        migrations.AddField(
            model_name="property",
            name="owner_cash_purchase_costs",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
        ),
        migrations.AddField(
            model_name="property",
            name="owner_cash_initial_repairs",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
        ),
        migrations.AddField(
            model_name="property",
            name="owner_cash_other_purchase_costs",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
        ),
        migrations.RunPython(backfill_owner_cash_out, migrations.RunPython.noop),
    ]
