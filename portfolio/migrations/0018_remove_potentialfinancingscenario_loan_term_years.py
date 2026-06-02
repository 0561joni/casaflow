from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("portfolio", "0017_move_potential_cash_out_to_scenarios"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="potentialfinancingscenario",
            name="loan_term_years",
        ),
    ]
