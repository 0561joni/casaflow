from decimal import Decimal

from django.db import migrations, models


def combine_purchase_cash_fields(apps, schema_editor):
    Property = apps.get_model("portfolio", "Property")
    db_alias = schema_editor.connection.alias
    for property_obj in Property.objects.using(db_alias).all():
        property_obj.cash_invested_at_purchase = (
            property_obj.owner_cash_down_payment
            + property_obj.owner_cash_purchase_costs
            + property_obj.owner_cash_initial_repairs
            + property_obj.owner_cash_other_purchase_costs
        ).quantize(Decimal("0.01"))
        property_obj.save(update_fields=["cash_invested_at_purchase"])


class Migration(migrations.Migration):
    dependencies = [
        ("portfolio", "0004_property_owner_cash_out"),
    ]

    operations = [
        migrations.AddField(
            model_name="property",
            name="cash_invested_at_purchase",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
        ),
        migrations.RunPython(combine_purchase_cash_fields, migrations.RunPython.noop),
        migrations.RemoveField(model_name="property", name="owner_cash_down_payment"),
        migrations.RemoveField(model_name="property", name="owner_cash_purchase_costs"),
        migrations.RemoveField(model_name="property", name="owner_cash_initial_repairs"),
        migrations.RemoveField(model_name="property", name="owner_cash_other_purchase_costs"),
        migrations.RemoveField(model_name="property", name="purchase_costs"),
    ]
