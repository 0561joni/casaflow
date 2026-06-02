from decimal import Decimal

from django.db import migrations


CENT = Decimal("0.01")


def owner_amounts_to_total_amounts(apps, schema_editor):
    Loan = apps.get_model("portfolio", "Loan")
    AnnualLoanSnapshot = apps.get_model("portfolio", "AnnualLoanSnapshot")
    db_alias = schema_editor.connection.alias
    for loan in Loan.objects.using(db_alias).select_related("property"):
        owner_share = loan.property.ownership_share
        if not owner_share:
            continue
        loan.original_amount = (loan.original_amount / owner_share).quantize(CENT)
        loan.save(update_fields=["original_amount"])
        for snapshot in AnnualLoanSnapshot.objects.using(db_alias).filter(loan=loan):
            snapshot.opening_balance = (snapshot.opening_balance / owner_share).quantize(CENT)
            snapshot.closing_balance = (snapshot.closing_balance / owner_share).quantize(CENT)
            snapshot.interest_paid = (snapshot.interest_paid / owner_share).quantize(CENT)
            snapshot.principal_paid = (snapshot.principal_paid / owner_share).quantize(CENT)
            snapshot.monthly_payment = (snapshot.monthly_payment / owner_share).quantize(CENT)
            snapshot.debt_service = (snapshot.debt_service / owner_share).quantize(CENT)
            snapshot.save(
                update_fields=[
                    "opening_balance",
                    "closing_balance",
                    "interest_paid",
                    "principal_paid",
                    "monthly_payment",
                    "debt_service",
                ]
            )


def total_amounts_to_owner_amounts(apps, schema_editor):
    Loan = apps.get_model("portfolio", "Loan")
    AnnualLoanSnapshot = apps.get_model("portfolio", "AnnualLoanSnapshot")
    db_alias = schema_editor.connection.alias
    for loan in Loan.objects.using(db_alias).select_related("property"):
        owner_share = loan.property.ownership_share
        loan.original_amount = (loan.original_amount * owner_share).quantize(CENT)
        loan.save(update_fields=["original_amount"])
        for snapshot in AnnualLoanSnapshot.objects.using(db_alias).filter(loan=loan):
            snapshot.opening_balance = (snapshot.opening_balance * owner_share).quantize(CENT)
            snapshot.closing_balance = (snapshot.closing_balance * owner_share).quantize(CENT)
            snapshot.interest_paid = (snapshot.interest_paid * owner_share).quantize(CENT)
            snapshot.principal_paid = (snapshot.principal_paid * owner_share).quantize(CENT)
            snapshot.monthly_payment = (snapshot.monthly_payment * owner_share).quantize(CENT)
            snapshot.debt_service = (snapshot.debt_service * owner_share).quantize(CENT)
            snapshot.save(
                update_fields=[
                    "opening_balance",
                    "closing_balance",
                    "interest_paid",
                    "principal_paid",
                    "monthly_payment",
                    "debt_service",
                ]
            )


class Migration(migrations.Migration):
    dependencies = [
        ("portfolio", "0006_cash_invested_total_amount"),
    ]

    operations = [
        migrations.RunPython(owner_amounts_to_total_amounts, total_amounts_to_owner_amounts),
    ]
