from decimal import Decimal

from django.db import migrations, models


def move_cash_out_to_scenarios(apps, schema_editor):
    PotentialDeal = apps.get_model("portfolio", "PotentialDeal")
    PotentialFinancingScenario = apps.get_model("portfolio", "PotentialFinancingScenario")
    for deal in PotentialDeal.objects.all():
        scenarios = list(PotentialFinancingScenario.objects.filter(deal=deal))
        if scenarios:
            PotentialFinancingScenario.objects.filter(deal=deal).update(personal_cash_out=deal.personal_cash_out)
            continue
        if deal.personal_cash_out:
            PotentialFinancingScenario.objects.create(
                deal=deal,
                name="Default scenario",
                personal_cash_out=deal.personal_cash_out,
                is_default=True,
            )


class Migration(migrations.Migration):

    dependencies = [
        ("portfolio", "0016_potential_deals"),
    ]

    operations = [
        migrations.AddField(
            model_name="potentialfinancingscenario",
            name="personal_cash_out",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
        ),
        migrations.RunPython(move_cash_out_to_scenarios, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="potentialdeal",
            name="personal_cash_out",
        ),
    ]
