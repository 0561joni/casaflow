from datetime import date

from django.db import migrations


def _history_start_year(property_obj, AnnualLoanSnapshot):
    candidates = []
    if property_obj.acquisition_date:
        candidates.append(property_obj.acquisition_date.year)
    snapshot_year = property_obj.annual_snapshots.order_by("year").values_list("year", flat=True).first()
    if snapshot_year:
        candidates.append(snapshot_year)
    loan_start = property_obj.loans.exclude(start_date__isnull=True).order_by("start_date").values_list("start_date", flat=True).first()
    if loan_start:
        candidates.append(loan_start.year)
    loan_snapshot_year = (
        AnnualLoanSnapshot.objects.filter(loan__property=property_obj)
        .order_by("year")
        .values_list("year", flat=True)
        .first()
    )
    if loan_snapshot_year:
        candidates.append(loan_snapshot_year)
    return min(candidates) if candidates else date.today().year


def backfill_property_snapshots(apps, schema_editor):
    Property = apps.get_model("portfolio", "Property")
    AnnualPropertySnapshot = apps.get_model("portfolio", "AnnualPropertySnapshot")
    AnnualLoanSnapshot = apps.get_model("portfolio", "AnnualLoanSnapshot")

    candidates = [date.today().year]
    snapshot_year = AnnualPropertySnapshot.objects.order_by("-year").values_list("year", flat=True).first()
    if snapshot_year:
        candidates.append(snapshot_year)
    loan_snapshot_year = AnnualLoanSnapshot.objects.order_by("-year").values_list("year", flat=True).first()
    if loan_snapshot_year:
        candidates.append(loan_snapshot_year)
    through_year = max(candidates)

    for property_obj in Property.objects.all():
        start_year = _history_start_year(property_obj, AnnualLoanSnapshot)
        if start_year > through_year:
            continue
        for year in range(start_year, through_year + 1):
            AnnualPropertySnapshot.objects.get_or_create(
                property=property_obj,
                year=year,
                defaults={
                    "property_value": property_obj.purchase_price,
                    "valuation_source": "Default purchase price",
                },
            )


class Migration(migrations.Migration):

    dependencies = [
        ("portfolio", "0012_tenant_admin_fields_leaseperson"),
    ]

    operations = [
        migrations.RunPython(backfill_property_snapshots, migrations.RunPython.noop),
    ]
