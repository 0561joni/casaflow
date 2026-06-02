# Generated manually for the initial real-estate finance schema.

import django.db.models.deletion
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="ImportRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("source_name", models.CharField(max_length=240)),
                ("status", models.CharField(default="completed", max_length=40)),
                ("warnings", models.JSONField(blank=True, default=list)),
                ("row_mappings", models.JSONField(blank=True, default=dict)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="Property",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=160)),
                ("address", models.TextField(blank=True)),
                ("ownership_share", models.DecimalField(decimal_places=6, default=Decimal("1.0"), max_digits=7)),
                ("purchase_price", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("purchase_costs", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("acquisition_date", models.DateField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
            ],
            options={"verbose_name_plural": "properties", "ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="AnnualPropertySnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("year", models.PositiveIntegerField()),
                ("property_value", models.DecimalField(decimal_places=2, max_digits=12)),
                ("vacancy_loss", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("manual_rent_adjustment", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("valuation_source", models.CharField(blank=True, max_length=160)),
                ("notes", models.TextField(blank=True)),
                ("property", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="annual_snapshots", to="portfolio.property")),
            ],
            options={"ordering": ["-year", "property__name"], "unique_together": {("property", "year")}},
        ),
        migrations.CreateModel(
            name="AnnualPropertyCost",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("category", models.CharField(choices=[("maintenance", "Maintenance"), ("management", "Management"), ("insurance", "Insurance"), ("property_tax", "Property tax"), ("utilities", "Utilities"), ("reserves", "Reserves"), ("other", "Other")], max_length=32)),
                ("amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("notes", models.CharField(blank=True, max_length=240)),
                ("snapshot", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="costs", to="portfolio.annualpropertysnapshot")),
            ],
            options={"ordering": ["snapshot", "category"], "unique_together": {("snapshot", "category")}},
        ),
        migrations.CreateModel(
            name="Loan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=160)),
                ("lender", models.CharField(blank=True, max_length=160)),
                ("original_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("start_date", models.DateField(blank=True, null=True)),
                ("maturity_date", models.DateField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                ("property", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="loans", to="portfolio.property")),
            ],
            options={"ordering": ["property__name", "name"]},
        ),
        migrations.CreateModel(
            name="AnnualLoanSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("year", models.PositiveIntegerField()),
                ("opening_balance", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("closing_balance", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("interest_paid", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("principal_paid", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("interest_rate", models.DecimalField(decimal_places=6, default=Decimal("0.00"), max_digits=7)),
                ("debt_service", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("rate_reset_date", models.DateField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                ("loan", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="annual_snapshots", to="portfolio.loan")),
            ],
            options={"ordering": ["-year", "loan__property__name", "loan__name"], "unique_together": {("loan", "year")}},
        ),
        migrations.CreateModel(
            name="ReportExport",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("export_type", models.CharField(choices=[("portfolio_pdf", "Portfolio PDF"), ("property_pdf", "Property PDF"), ("loan_pdf", "Loan PDF"), ("excel", "Excel"), ("csv", "CSV"), ("backup", "Backup")], max_length=40)),
                ("title", models.CharField(max_length=200)),
                ("file_name", models.CharField(blank=True, max_length=240)),
                ("year", models.PositiveIntegerField(blank=True, null=True)),
                ("property", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="portfolio.property")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="Tenant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("first_name", models.CharField(blank=True, max_length=120)),
                ("last_name", models.CharField(max_length=120)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("phone", models.CharField(blank=True, max_length=80)),
                ("notes", models.TextField(blank=True)),
            ],
            options={"ordering": ["last_name", "first_name"]},
        ),
        migrations.CreateModel(
            name="Unit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("label", models.CharField(max_length=120)),
                ("floor", models.CharField(blank=True, max_length=40)),
                ("area_sqm", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ("notes", models.TextField(blank=True)),
                ("property", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="units", to="portfolio.property")),
            ],
            options={"ordering": ["property__name", "label"], "unique_together": {("property", "label")}},
        ),
        migrations.CreateModel(
            name="Lease",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("start_date", models.DateField()),
                ("end_date", models.DateField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("notes", models.TextField(blank=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="leases", to="portfolio.tenant")),
                ("unit", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="leases", to="portfolio.unit")),
            ],
            options={"ordering": ["unit__property__name", "unit__label", "-start_date"]},
        ),
        migrations.CreateModel(
            name="RentPeriod",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("effective_start", models.DateField()),
                ("effective_end", models.DateField(blank=True, null=True)),
                ("cold_rent", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10)),
                ("utility_prepayment", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10)),
                ("total_rent", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10)),
                ("notes", models.TextField(blank=True)),
                ("lease", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="rent_periods", to="portfolio.lease")),
            ],
            options={"ordering": ["lease__unit__property__name", "lease__unit__label", "-effective_start"]},
        ),
    ]
