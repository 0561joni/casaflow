from decimal import Decimal

from django.db import migrations


def owner_amount_to_total_amount(apps, schema_editor):
    Property = apps.get_model("portfolio", "Property")
    db_alias = schema_editor.connection.alias
    for property_obj in Property.objects.using(db_alias).all():
        if property_obj.ownership_share:
            property_obj.cash_invested_at_purchase = (property_obj.cash_invested_at_purchase / property_obj.ownership_share).quantize(Decimal("0.01"))
            property_obj.save(update_fields=["cash_invested_at_purchase"])


def total_amount_to_owner_amount(apps, schema_editor):
    Property = apps.get_model("portfolio", "Property")
    db_alias = schema_editor.connection.alias
    for property_obj in Property.objects.using(db_alias).all():
        property_obj.cash_invested_at_purchase = (property_obj.cash_invested_at_purchase * property_obj.ownership_share).quantize(Decimal("0.01"))
        property_obj.save(update_fields=["cash_invested_at_purchase"])


class Migration(migrations.Migration):
    dependencies = [
        ("portfolio", "0005_simplify_purchase_cash"),
    ]

    operations = [
        migrations.RunPython(owner_amount_to_total_amount, total_amount_to_owner_amount),
    ]
