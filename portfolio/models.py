from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


ZERO = Decimal("0.00")
CENT = Decimal("0.01")


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AppSettings(TimeStampedModel):
    ENGLISH = "en"
    GERMAN = "de"
    LANGUAGE_CHOICES = [
        (ENGLISH, "English"),
        (GERMAN, "Deutsch"),
    ]

    language_code = models.CharField(max_length=8, choices=LANGUAGE_CHOICES, default=ENGLISH)
    tax_calculations_enabled = models.BooleanField(default=True)
    effective_tax_rate = models.DecimalField(max_digits=7, decimal_places=6, default=Decimal("0.000000"))
    tax_loss_benefit_enabled = models.BooleanField(default=True)
    landlord_name = models.CharField(max_length=160, blank=True)
    landlord_street = models.CharField(max_length=200, blank=True)
    landlord_zip = models.CharField(max_length=20, blank=True)
    landlord_city = models.CharField(max_length=120, blank=True)
    landlord_phone = models.CharField(max_length=80, blank=True)
    landlord_fax = models.CharField(max_length=80, blank=True)
    landlord_email = models.EmailField(blank=True)

    class Meta:
        verbose_name = "app settings"
        verbose_name_plural = "app settings"

    def __str__(self):
        return "CasaFlow settings"

    @classmethod
    def load(cls):
        settings_obj, _ = cls.objects.get_or_create(pk=1)
        return settings_obj


class AnnualPortfolioTax(TimeStampedModel):
    year = models.PositiveIntegerField(unique=True)
    tax_deductible_costs = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-year"]
        verbose_name = "annual portfolio tax"
        verbose_name_plural = "annual portfolio taxes"

    def __str__(self):
        return f"Portfolio tax {self.year}"


class LandlordProfile(TimeStampedModel):
    name = models.CharField(max_length=160)
    street_address = models.CharField(max_length=200)
    postal_code = models.CharField(max_length=20, blank=True)
    city = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=80, blank=True)
    fax = models.CharField(max_length=80, blank=True)
    email = models.EmailField(blank=True)
    signature_image = models.FileField(upload_to="landlord_signatures/", blank=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_default", "name"]
        constraints = [
            models.UniqueConstraint(fields=["is_default"], condition=Q(is_default=True), name="unique_default_landlord_profile"),
        ]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default:
            LandlordProfile.objects.exclude(pk=self.pk).filter(is_default=True).update(is_default=False)

    def __str__(self):
        return self.name


class Property(TimeStampedModel):
    APARTMENT = "apartment"
    SINGLE_FAMILY_HOUSE = "single_family_house"
    MULTI_FAMILY_HOUSE = "multi_family_house"
    MIXED_USE = "mixed_use"
    COMMERCIAL = "commercial"
    LAND = "land"
    OTHER = "other"
    OBJECT_TYPES = [
        (APARTMENT, "Apartment"),
        (SINGLE_FAMILY_HOUSE, "Single-family house"),
        (MULTI_FAMILY_HOUSE, "Multi-family house"),
        (MIXED_USE, "Mixed-use property"),
        (COMMERCIAL, "Commercial property"),
        (LAND, "Land"),
        (OTHER, "Other"),
    ]

    name = models.CharField(max_length=160)
    object_type = models.CharField(max_length=40, choices=OBJECT_TYPES, blank=True)
    address = models.TextField(blank=True)
    street_address = models.CharField(max_length=200, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    city = models.CharField(max_length=120, blank=True)
    photo = models.FileField(upload_to="property_photos/", blank=True)
    ownership_share = models.DecimalField(max_digits=7, decimal_places=6, default=Decimal("1.0"))
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    cash_invested_at_purchase = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    recurring_expense_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    acquisition_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "properties"

    def __str__(self):
        return self.name

    @property
    def display_address(self):
        structured = ", ".join(part for part in [self.street_address, " ".join(part for part in [self.postal_code, self.city] if part)] if part)
        return structured or self.address


class Unit(TimeStampedModel):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="units")
    label = models.CharField(max_length=120)
    floor = models.CharField(max_length=40, blank=True)
    area_sqm = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["property__name", "label"]
        unique_together = [("property", "label")]

    def __str__(self):
        return f"{self.property.name} - {self.label}"


class PropertyAdministration(TimeStampedModel):
    property = models.OneToOneField(Property, on_delete=models.CASCADE, related_name="administration")
    postal_code = models.CharField(max_length=20, blank=True)
    construction_year = models.PositiveIntegerField(null=True, blank=True)
    total_building_area_sqm = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.property.name} administration"


class UnitAdministration(TimeStampedModel):
    unit = models.OneToOneField(Unit, on_delete=models.CASCADE, related_name="administration")
    apartment_number = models.CharField(max_length=80, blank=True)
    cellar_number = models.CharField(max_length=80, blank=True)
    ownership_share_text = models.CharField(max_length=120, blank=True)
    monthly_house_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.unit} administration"


class UnitLandRegistry(TimeStampedModel):
    unit = models.OneToOneField(Unit, on_delete=models.CASCADE, related_name="land_registry")
    local_court = models.CharField(max_length=160, blank=True)
    land_register_district = models.CharField(max_length=160, blank=True)
    sheet_number = models.CharField(max_length=80, blank=True)
    cadastral_district = models.CharField(max_length=80, blank=True)
    plot_numbers = models.CharField(max_length=160, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.unit} land registry"


class UnitTechnicalInfo(TimeStampedModel):
    unit = models.OneToOneField(Unit, on_delete=models.CASCADE, related_name="technical_info")
    heating_type = models.CharField(max_length=160, blank=True)
    boiler_installation_info = models.CharField(max_length=160, blank=True)
    instant_water_heater_info = models.CharField(max_length=160, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.unit} technical info"


class Contact(TimeStampedModel):
    PROPERTY_MANAGEMENT = "property_management"
    OTHER = "other"
    CONTACT_TYPES = [
        (PROPERTY_MANAGEMENT, "Property management"),
        (OTHER, "Other"),
    ]

    contact_type = models.CharField(max_length=40, choices=CONTACT_TYPES, default=PROPERTY_MANAGEMENT)
    name = models.CharField(max_length=160)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=80, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class UnitContact(TimeStampedModel):
    PROPERTY_MANAGEMENT = "property_management"
    OTHER = "other"
    CONTACT_ROLES = [
        (PROPERTY_MANAGEMENT, "Property management"),
        (OTHER, "Other"),
    ]

    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="contacts")
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="unit_links")
    role = models.CharField(max_length=40, choices=CONTACT_ROLES, default=PROPERTY_MANAGEMENT)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["unit__property__name", "unit__label", "role", "contact__name"]
        unique_together = [("unit", "contact", "role")]

    def __str__(self):
        return f"{self.unit} - {self.contact}"


class Tenant(TimeStampedModel):
    first_name = models.CharField(max_length=120, blank=True)
    last_name = models.CharField(max_length=120)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=80, blank=True)
    support_office_name = models.CharField("financial support office name", max_length=160, blank=True)
    support_office_email = models.EmailField("financial support office email", blank=True)
    support_office_phone = models.CharField("financial support office phone", max_length=80, blank=True)
    birthday = models.DateField(null=True, blank=True)
    relationship_notes = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.last_name}, {self.first_name}".strip(", ")


class Lease(TimeStampedModel):
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="leases")
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="leases")
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["unit__property__name", "unit__label", "-start_date"]

    def clean(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValidationError("Lease end date must be on or after the start date.")

    def __str__(self):
        return f"{self.unit} / {self.tenant}"


class LeasePerson(TimeStampedModel):
    PRIMARY = "primary"
    CO_TENANT = "co_tenant"
    OCCUPANT = "occupant"
    CHILD = "child"
    OTHER = "other"
    ROLES = [
        (PRIMARY, "Primary contract tenant"),
        (CO_TENANT, "Co-contract tenant"),
        (OCCUPANT, "Occupant"),
        (CHILD, "Child"),
        (OTHER, "Other"),
    ]
    CONTRACT_ROLES = {PRIMARY, CO_TENANT}

    lease = models.ForeignKey(Lease, on_delete=models.CASCADE, related_name="people")
    person = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="lease_links")
    role = models.CharField(max_length=40, choices=ROLES, default=PRIMARY)
    move_in_date = models.DateField()
    move_out_date = models.DateField(null=True, blank=True)
    is_contract_signer = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["lease__unit__property__name", "lease__unit__label", "role", "person__last_name", "person__first_name"]
        unique_together = [("lease", "person", "role")]

    def clean(self):
        if self.move_out_date and self.move_out_date < self.move_in_date:
            raise ValidationError("Move-out date must be on or after move-in date.")
        if self.lease_id:
            if self.move_in_date and self.move_in_date < self.lease.start_date:
                raise ValidationError("Move-in date cannot be before the lease starts.")
            if self.lease.end_date and self.move_in_date and self.move_in_date > self.lease.end_date:
                raise ValidationError("Move-in date cannot be after the lease ends.")
            if self.lease.end_date and self.move_out_date and self.move_out_date > self.lease.end_date:
                raise ValidationError("Move-out date cannot be after the lease ends.")

    def save(self, *args, **kwargs):
        self.is_contract_signer = self.role in self.CONTRACT_ROLES
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.lease}: {self.person} ({self.get_role_display()})"


class RentPeriod(TimeStampedModel):
    lease = models.ForeignKey(Lease, on_delete=models.CASCADE, related_name="rent_periods")
    effective_start = models.DateField()
    effective_end = models.DateField(null=True, blank=True)
    cold_rent = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)
    utility_prepayment = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)
    total_rent = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["lease__unit__property__name", "lease__unit__label", "-effective_start"]

    def clean(self):
        if self.effective_end and self.effective_end < self.effective_start:
            raise ValidationError("Rent period end date must be on or after the start date.")
        qs = RentPeriod.objects.filter(lease=self.lease)
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        overlapping = qs.filter(
            effective_start__lte=self.effective_end or "9999-12-31",
        ).filter(Q(effective_end__isnull=True) | Q(effective_end__gte=self.effective_start))
        if overlapping.exists():
            raise ValidationError("Rent periods for a lease must not overlap.")

    def save(self, *args, **kwargs):
        if not self.total_rent:
            self.total_rent = self.cold_rent + self.utility_prepayment
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.lease}: {self.effective_start}"


class AnnualPropertySnapshot(TimeStampedModel):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="annual_snapshots")
    year = models.PositiveIntegerField()
    property_value = models.DecimalField(max_digits=12, decimal_places=2)
    vacancy_loss = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    manual_rent_adjustment = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    valuation_source = models.CharField(max_length=160, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-year", "property__name"]
        unique_together = [("property", "year")]

    def __str__(self):
        return f"{self.property.name} {self.year}"


class AnnualPropertyCost(TimeStampedModel):
    MAINTENANCE = "maintenance"
    MANAGEMENT = "management"
    INSURANCE = "insurance"
    PROPERTY_TAX = "property_tax"
    UTILITIES = "utilities"
    RESERVES = "reserves"
    OTHER = "other"

    COST_CATEGORIES = [
        (MAINTENANCE, "Maintenance"),
        (MANAGEMENT, "Management"),
        (INSURANCE, "Insurance"),
        (PROPERTY_TAX, "Property tax"),
        (UTILITIES, "Utilities"),
        (RESERVES, "Reserves"),
        (OTHER, "Other"),
    ]

    snapshot = models.ForeignKey(AnnualPropertySnapshot, on_delete=models.CASCADE, related_name="costs")
    category = models.CharField(max_length=32, choices=COST_CATEGORIES)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    notes = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ["snapshot", "category"]
        unique_together = [("snapshot", "category")]

    def __str__(self):
        return f"{self.snapshot} {self.get_category_display()}"


class Loan(TimeStampedModel):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="loans")
    name = models.CharField(max_length=160)
    lender = models.CharField(max_length=160, blank=True)
    original_amount = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    default_interest_rate = models.DecimalField(max_digits=7, decimal_places=6, default=ZERO)
    default_monthly_payment = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    start_date = models.DateField(null=True, blank=True)
    maturity_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["property__name", "name"]

    def __str__(self):
        return f"{self.property.name} - {self.name}"


class AnnualLoanSnapshot(TimeStampedModel):
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name="annual_snapshots")
    year = models.PositiveIntegerField()
    opening_balance = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    closing_balance = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    interest_paid = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    principal_paid = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    interest_rate = models.DecimalField(max_digits=7, decimal_places=6, default=ZERO)
    monthly_payment = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    debt_service = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    rate_reset_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-year", "loan__property__name", "loan__name"]
        unique_together = [("loan", "year")]

    def clean(self):
        if self.opening_balance < 0 or self.closing_balance < 0:
            raise ValidationError("Loan balances cannot be negative.")
        if self.closing_balance > self.opening_balance:
            raise ValidationError("Closing balance cannot exceed opening balance.")
        if self.interest_paid < 0 or self.principal_paid < 0:
            raise ValidationError("Loan payments cannot be negative.")
        if self.monthly_payment is not None and self.monthly_payment < 0:
            raise ValidationError("Loan payments cannot be negative.")
        if self.debt_service is not None and self.debt_service < 0:
            raise ValidationError("Loan payments cannot be negative.")

    def save(self, *args, **kwargs):
        if self.monthly_payment is None:
            self.monthly_payment = ZERO
        if not self.debt_service and self.monthly_payment:
            self.debt_service = (self.monthly_payment * Decimal("12")).quantize(CENT)
        elif not self.debt_service:
            self.debt_service = self.interest_paid + self.principal_paid
        if not self.monthly_payment and self.debt_service:
            self.monthly_payment = (self.debt_service / Decimal("12")).quantize(CENT)
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.loan} {self.year}"


class PotentialDeal(TimeStampedModel):
    DRAFT = "draft"
    REVIEW = "review"
    INTERESTING = "interesting"
    REJECTED = "rejected"
    STATUS_CHOICES = [
        (DRAFT, "Draft"),
        (REVIEW, "Review"),
        (INTERESTING, "Interesting"),
        (REJECTED, "Rejected"),
    ]

    name = models.CharField(max_length=160)
    address = models.TextField(blank=True)
    status = models.CharField(max_length=40, choices=STATUS_CHOICES, default=DRAFT)
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    ownership_share = models.DecimalField(max_digits=7, decimal_places=6, default=Decimal("1.0"))
    expected_monthly_cold_rent = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)
    expected_monthly_utility_prepayment = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)
    yearly_non_recoverable_costs = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    buying_costs = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO, blank=True)
    minimum_dscr = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    maximum_ltv = models.DecimalField(max_digits=7, decimal_places=6, null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class PotentialFinancingScenario(TimeStampedModel):
    deal = models.ForeignKey(PotentialDeal, on_delete=models.CASCADE, related_name="scenarios")
    name = models.CharField(max_length=160)
    owner_cash_out = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    loan_amount = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    interest_rate = models.DecimalField(max_digits=7, decimal_places=6, default=ZERO)
    monthly_payment = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    maturity_notes = models.CharField(max_length=240, blank=True)
    is_default = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["deal__name", "-is_default", "name"]

    def __str__(self):
        return f"{self.deal.name} - {self.name}"


class ImportRun(TimeStampedModel):
    source_name = models.CharField(max_length=240)
    status = models.CharField(max_length=40, default="completed")
    warnings = models.JSONField(default=list, blank=True)
    row_mappings = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.source_name} {self.created_at:%Y-%m-%d %H:%M}"


class ReportExport(TimeStampedModel):
    EXPORT_TYPES = [
        ("bank_financing_pdf", "Bank Financing PDF"),
        ("bank_financing_excel", "Bank Financing Excel"),
        ("mietbescheinigung_pdf", "Mietbescheinigung PDF"),
        ("backup", "Backup"),
    ]

    export_type = models.CharField(max_length=40, choices=EXPORT_TYPES)
    title = models.CharField(max_length=200)
    file_name = models.CharField(max_length=240, blank=True)
    year = models.PositiveIntegerField(null=True, blank=True)
    property = models.ForeignKey(Property, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["export_type", "file_name"], name="unique_export_type_file_name"),
        ]

    def __str__(self):
        return self.title
