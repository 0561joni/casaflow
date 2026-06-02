from decimal import Decimal

from django.db import migrations, models


def migrate_other_costs_to_property(apps, schema_editor):
    Property = apps.get_model("portfolio", "Property")
    AnnualPropertyCost = apps.get_model("portfolio", "AnnualPropertyCost")
    db_alias = schema_editor.connection.alias
    for property_obj in Property.objects.using(db_alias).all():
        cost = (
            AnnualPropertyCost.objects.using(db_alias)
            .filter(snapshot__property=property_obj, category="other", notes__icontains="Imported annual running costs")
            .order_by("-snapshot__year")
            .first()
        )
        if cost and cost.amount:
            property_obj.recurring_expense_amount = cost.amount
            property_obj.save(update_fields=["recurring_expense_amount"])
            AnnualPropertyCost.objects.using(db_alias).filter(
                snapshot__property=property_obj,
                category="other",
                notes__icontains="Imported annual running costs",
            ).update(amount=Decimal("0.00"), notes="Migrated to property yearly recurring expense")


class Migration(migrations.Migration):
    dependencies = [
        ("portfolio", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="property",
            name="recurring_expense_amount",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.RunPython(migrate_other_costs_to_property, migrations.RunPython.noop),
    ]
