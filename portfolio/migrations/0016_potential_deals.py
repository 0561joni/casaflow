from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("portfolio", "0015_property_photo"),
    ]

    operations = [
        migrations.CreateModel(
            name="PotentialDeal",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=160)),
                ("address", models.TextField(blank=True)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("review", "Review"), ("interesting", "Interesting"), ("rejected", "Rejected")], default="draft", max_length=40)),
                ("purchase_price", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("ownership_share", models.DecimalField(decimal_places=6, default=Decimal("1.0"), max_digits=7)),
                ("personal_cash_out", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("expected_monthly_cold_rent", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10)),
                ("expected_monthly_utility_prepayment", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10)),
                ("yearly_non_recoverable_costs", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("notes", models.TextField(blank=True)),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="PotentialFinancingScenario",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=160)),
                ("loan_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("interest_rate", models.DecimalField(decimal_places=6, default=Decimal("0.00"), max_digits=7)),
                ("monthly_payment", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("loan_term_years", models.PositiveIntegerField(blank=True, null=True)),
                ("maturity_notes", models.CharField(blank=True, max_length=240)),
                ("is_default", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True)),
                ("deal", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="scenarios", to="portfolio.potentialdeal")),
            ],
            options={
                "ordering": ["deal__name", "-is_default", "name"],
            },
        ),
    ]
