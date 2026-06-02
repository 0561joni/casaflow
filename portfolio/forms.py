from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django import forms
from django.db import transaction
from django.db.models import Q

from .models import (
    AnnualLoanSnapshot,
    AnnualPropertyCost,
    AnnualPropertySnapshot,
    AnnualPortfolioTax,
    AppSettings,
    Contact,
    LandlordProfile,
    Lease,
    LeasePerson,
    Loan,
    PotentialDeal,
    PotentialFinancingScenario,
    Property,
    PropertyAdministration,
    RentPeriod,
    Tenant,
    Unit,
    UnitAdministration,
    UnitContact,
    UnitLandRegistry,
    UnitTechnicalInfo,
)


ZERO = Decimal("0.00")
CENT = Decimal("0.01")


def _format_property_address(street_address: str, postal_code: str, city: str) -> str:
    street_address = (street_address or "").strip()
    postal_city = " ".join(part for part in [(postal_code or "").strip(), (city or "").strip()] if part)
    return "\n".join(part for part in [street_address, postal_city] if part)


class CurrencyInput(forms.NumberInput):
    input_type = "number"

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("attrs", {"step": "0.01", "min": "0"})
        super().__init__(*args, **kwargs)


class DecimalTextInput(forms.TextInput):
    def __init__(self, *args, **kwargs):
        attrs = kwargs.pop("attrs", {})
        attrs.setdefault("inputmode", "decimal")
        super().__init__(*args, attrs=attrs, **kwargs)


class FlexibleDecimalField(forms.DecimalField):
    def to_python(self, value):
        if isinstance(value, str):
            value = value.strip().replace(" ", "").replace(",", ".")
        return super().to_python(value)


class PercentageRateField(forms.Field):
    widget = DecimalTextInput

    default_error_messages = {
        "invalid": "Enter a valid percentage.",
        "negative": "Enter a positive percentage.",
        "max_decimal_places": "Enter at most 4 decimal places.",
    }

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", DecimalTextInput(attrs={"placeholder": "2.0000"}))
        super().__init__(*args, **kwargs)

    def prepare_value(self, value):
        if value in self.empty_values:
            return ""
        if isinstance(value, str):
            return value
        try:
            percent_value = Decimal(value) * Decimal("100")
        except (InvalidOperation, TypeError, ValueError):
            return value
        return format(percent_value.quantize(Decimal("0.0001")), "f")

    def clean(self, value):
        value = super().clean(value)
        if value in self.empty_values:
            if self.required:
                raise forms.ValidationError(self.error_messages["required"], code="required")
            return None
        if isinstance(value, str):
            value = value.strip().replace(" ", "").replace("%", "").replace(",", ".")
        try:
            percent_value = Decimal(value)
        except (InvalidOperation, TypeError, ValueError):
            raise forms.ValidationError(self.error_messages["invalid"], code="invalid")
        if percent_value < 0:
            raise forms.ValidationError(self.error_messages["negative"], code="negative")
        exponent = percent_value.as_tuple().exponent
        if exponent < -4:
            raise forms.ValidationError(self.error_messages["max_decimal_places"], code="max_decimal_places")
        return (percent_value / Decimal("100")).quantize(Decimal("0.000001"))


def parse_flexible_date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    for date_format in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, date_format).date()
        except (TypeError, ValueError):
            continue
    return None


class FlexibleDateField(forms.DateField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("input_formats", ["%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"])
        kwargs.setdefault("widget", forms.DateInput(format="%d.%m.%Y", attrs={"placeholder": "DD.MM.YYYY"}))
        super().__init__(*args, **kwargs)


class AppSettingsForm(forms.ModelForm):
    language_code = forms.ChoiceField(
        choices=AppSettings.LANGUAGE_CHOICES,
        required=False,
        label="Language",
        help_text="Choose the app language.",
    )
    effective_tax_rate = PercentageRateField(
        required=False,
        label="Effective tax rate",
        help_text="Enter the estimated income tax rate as a percentage, e.g. 30 for 30%.",
    )

    class Meta:
        model = AppSettings
        fields = [
            "language_code",
            "tax_calculations_enabled",
            "effective_tax_rate",
            "tax_loss_benefit_enabled",
        ]
        labels = {
            "language_code": "Language",
            "tax_calculations_enabled": "Enable tax calculations",
            "tax_loss_benefit_enabled": "Apply tax benefit on losses",
        }
        widgets = {
            "language_code": forms.Select(),
        }
        help_texts = {
            "language_code": "Choose the app language.",
            "tax_calculations_enabled": "When disabled, Dashboard tax toggles, tax badges, and tax bridge details are hidden.",
            "tax_loss_benefit_enabled": "When a property has a tax loss, CasaFlow estimates the benefit using the same effective tax rate.",
        }

    def clean_effective_tax_rate(self):
        if "effective_tax_rate" not in self.data:
            return self.instance.effective_tax_rate if self.instance and self.instance.pk else ZERO
        return self.cleaned_data["effective_tax_rate"] or ZERO

    def clean_language_code(self):
        if "language_code" not in self.data:
            return self.instance.language_code if self.instance and self.instance.pk else AppSettings.ENGLISH
        return self.cleaned_data["language_code"] or AppSettings.ENGLISH

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("tax_calculations_enabled"):
            if self.instance and self.instance.pk:
                cleaned_data["effective_tax_rate"] = self.instance.effective_tax_rate
                cleaned_data["tax_loss_benefit_enabled"] = self.instance.tax_loss_benefit_enabled
        return cleaned_data


class AnnualPortfolioTaxSettingsForm(forms.Form):
    def __init__(self, *args, years=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.years = list(years or [])
        existing_rows = {
            row.year: row
            for row in AnnualPortfolioTax.objects.filter(year__in=self.years)
        }
        for year in self.years:
            row = existing_rows.get(year)
            costs_name = f"tax_deductible_costs_{year}"
            notes_name = f"tax_notes_{year}"
            self.fields[costs_name] = FlexibleDecimalField(
                max_digits=12,
                decimal_places=2,
                min_value=ZERO,
                required=False,
                label=f"{year} tax-deductible costs",
                initial=row.tax_deductible_costs if row else ZERO,
                widget=CurrencyInput(),
            )
            self.fields[notes_name] = forms.CharField(
                required=False,
                label=f"{year} notes",
                initial=row.notes if row else "",
                widget=forms.Textarea(attrs={"rows": 1}),
            )
        self.rows = [
            {
                "year": year,
                "costs": self[f"tax_deductible_costs_{year}"],
                "notes": self[f"tax_notes_{year}"],
            }
            for year in self.years
        ]

    def save(self):
        for year in self.years:
            tax_deductible_costs = self.cleaned_data.get(f"tax_deductible_costs_{year}") or ZERO
            notes = self.cleaned_data.get(f"tax_notes_{year}", "")
            if tax_deductible_costs or notes:
                AnnualPortfolioTax.objects.update_or_create(
                    year=year,
                    defaults={
                        "tax_deductible_costs": tax_deductible_costs,
                        "notes": notes,
                    },
                )
            else:
                AnnualPortfolioTax.objects.filter(year=year).delete()


MIETBESCHEINIGUNG_TEMPLATES = [
    ("jobcenter", "Jobcenter"),
    ("stadt_kassel", "Stadt Kassel"),
]


class MietbescheinigungForm(forms.Form):
    template = forms.ChoiceField(choices=MIETBESCHEINIGUNG_TEMPLATES, label="Template")
    landlord_profile = forms.ChoiceField(required=False, label="Landlord")

    landlord_name = forms.CharField(max_length=160, label="Landlord name")
    landlord_street = forms.CharField(max_length=200, label="Landlord street / address")
    landlord_zip = forms.CharField(max_length=20, required=False, label="Landlord ZIP")
    landlord_city = forms.CharField(max_length=120, required=False, label="Landlord city")
    landlord_phone = forms.CharField(max_length=80, required=False, label="Landlord phone")
    landlord_fax = forms.CharField(max_length=80, required=False, label="Landlord fax")
    landlord_email = forms.EmailField(required=False, label="Landlord email")
    signature_image = forms.FileField(required=False, label="Signature image")
    include_signature = forms.BooleanField(required=False, label="Include signature in PDF")

    tenant_name = forms.CharField(max_length=240, label="Contract tenant")
    tenant_street = forms.CharField(max_length=200, label="Rental street / house number")
    tenant_zip = forms.CharField(max_length=20, required=False, label="Rental ZIP")
    tenant_city = forms.CharField(max_length=120, required=False, label="Rental city")
    tenant_contact = forms.CharField(max_length=200, required=False, label="Tenant phone / email")

    lease_start = FlexibleDateField(label="Move-in / lease start")
    tenant_count = forms.IntegerField(min_value=0, required=False, label="Contract tenant count")
    floor = forms.CharField(max_length=80, required=False, label="Floor / location in building")
    construction_year = forms.IntegerField(min_value=0, required=False, label="Construction year")
    building_area_sqm = forms.DecimalField(max_digits=10, decimal_places=2, min_value=ZERO, required=False, label="Total building area sqm")
    living_area_sqm = forms.DecimalField(max_digits=8, decimal_places=2, min_value=ZERO, required=False, label="Living area sqm")
    rooms = forms.DecimalField(max_digits=5, decimal_places=1, min_value=ZERO, required=False, label="Rooms")

    rent_valid_from = FlexibleDateField(label="Rent valid from")
    cold_rent = forms.DecimalField(max_digits=10, decimal_places=2, min_value=ZERO, widget=CurrencyInput(), label="Cold rent")
    operating_costs = forms.DecimalField(max_digits=10, decimal_places=2, min_value=ZERO, widget=CurrencyInput(), label="Operating costs / utilities")
    total_rent = forms.DecimalField(max_digits=10, decimal_places=2, min_value=ZERO, widget=CurrencyInput(), label="Total rent")

    heating_costs = forms.DecimalField(max_digits=10, decimal_places=2, min_value=ZERO, required=False, widget=CurrencyInput(), label="Heating costs")
    warm_water_costs = forms.DecimalField(max_digits=10, decimal_places=2, min_value=ZERO, required=False, widget=CurrencyInput(), label="Warm water costs")
    garage_cost = forms.DecimalField(max_digits=10, decimal_places=2, min_value=ZERO, required=False, widget=CurrencyInput(), label="Garage cost")
    parking_cost = forms.DecimalField(max_digits=10, decimal_places=2, min_value=ZERO, required=False, widget=CurrencyInput(), label="Parking cost")
    arrears_amount = forms.DecimalField(max_digits=10, decimal_places=2, min_value=ZERO, required=False, widget=CurrencyInput(), label="Rent arrears")

    is_sublease = forms.BooleanField(required=False, label="Sublease")
    public_funded = forms.BooleanField(required=False, label="Publicly funded housing")
    operating_costs_advance = forms.BooleanField(required=False, initial=True, label="Operating costs are advance payments with annual settlement")
    heating_in_total_rent = forms.BooleanField(required=False, label="Heating costs are included in total rent")
    warm_water_in_total_rent = forms.BooleanField(required=False, label="Warm water costs are included in total rent")
    garage_in_total_rent = forms.BooleanField(required=False, label="Garage is included in total rent")
    parking_in_total_rent = forms.BooleanField(required=False, label="Parking is included in total rent")
    arrears_existing = forms.BooleanField(required=False, label="Rent arrears exist")
    rent_reduction = forms.BooleanField(required=False, label="Rent reduction agreed")

    issue_place = forms.CharField(max_length=120, required=False, label="Place")
    issue_date = FlexibleDateField(label="Date")

    def __init__(self, *args, landlord_profiles=None, **kwargs):
        super().__init__(*args, **kwargs)
        landlord_profiles = list(landlord_profiles or [])
        self.fields["landlord_profile"].choices = [
            (str(profile.pk), f"{profile.name}{' (default)' if profile.is_default else ''}")
            for profile in landlord_profiles
        ] + [("__new__", "New landlord")]


class PropertyForm(forms.ModelForm):
    acquisition_date = FlexibleDateField(required=False, help_text="Use DD.MM.YYYY.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["purchase_price"].help_text = "Full property purchase price. Used for context and yield calculations."
        self.fields["cash_invested_at_purchase"].label = "Total cash invested at purchase"
        self.fields["cash_invested_at_purchase"].help_text = "Total property-level cash invested at purchase: down payment, buyer costs, notary, taxes, broker, initial repairs, and other purchase-related cash. The app calculates your share from the ownership share."
        self.fields["recurring_expense_amount"].label = "Yearly recurring expense"
        self.fields["recurring_expense_amount"].help_text = "Full-property annual non-recoverable expense. Leave blank to use 5% of annual cold rent."

    class Meta:
        model = Property
        fields = [
            "name",
            "object_type",
            "address",
            "street_address",
            "postal_code",
            "city",
            "ownership_share",
            "purchase_price",
            "cash_invested_at_purchase",
            "recurring_expense_amount",
            "acquisition_date",
            "notes",
        ]
        widgets = {
            "ownership_share": forms.NumberInput(attrs={"step": "0.000001", "min": "0", "max": "1"}),
            "purchase_price": CurrencyInput(),
            "cash_invested_at_purchase": CurrencyInput(),
            "recurring_expense_amount": CurrencyInput(),
            "address": forms.Textarea(attrs={"rows": 2}),
        }


class PropertyCreateForm(forms.ModelForm):
    acquisition_date = FlexibleDateField(required=False, help_text="Use DD.MM.YYYY.")
    construction_year = forms.IntegerField(min_value=0, required=False)
    total_building_area_sqm = forms.DecimalField(max_digits=10, decimal_places=2, min_value=ZERO, required=False, label="Total property area")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cash_invested_at_purchase"].label = "Your Cash Invested"
        self.fields["cash_invested_at_purchase"].help_text = "Total cash invested at purchase. The app calculates your share from the ownership share."
        self.fields["recurring_expense_amount"].label = "Yearly recurring expense"
        self.fields["recurring_expense_amount"].help_text = "Full-property annual non-recoverable expense. Leave blank to use 5% of annual cold rent."

    class Meta:
        model = Property
        fields = [
            "name",
            "street_address",
            "postal_code",
            "city",
            "object_type",
            "ownership_share",
            "purchase_price",
            "cash_invested_at_purchase",
            "acquisition_date",
            "photo",
            "recurring_expense_amount",
            "notes",
        ]
        widgets = {
            "ownership_share": forms.NumberInput(attrs={"step": "0.000001", "min": "0", "max": "1"}),
            "purchase_price": CurrencyInput(),
            "cash_invested_at_purchase": CurrencyInput(),
            "recurring_expense_amount": CurrencyInput(),
            "photo": forms.FileInput(),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "purchase_price": "Purchase price",
            "street_address": "Street / house number",
            "postal_code": "ZIP",
            "city": "City",
        }
        help_texts = {
            "purchase_price": "Full-property purchase price.",
            "ownership_share": "Your ownership share as a decimal, e.g. 0.5 for 50%.",
        }

    def save(self, commit=True):
        with transaction.atomic():
            property_obj = super().save(commit=False)
            property_obj.address = _format_property_address(property_obj.street_address, property_obj.postal_code, property_obj.city)
            if commit:
                property_obj.save()
            if commit:
                PropertyAdministration.objects.update_or_create(
                    property=property_obj,
                    defaults={
                        "construction_year": self.cleaned_data["construction_year"],
                        "total_building_area_sqm": self.cleaned_data["total_building_area_sqm"],
                    },
                )
            return property_obj


class PropertyDossierForm(forms.ModelForm):
    construction_year = forms.IntegerField(min_value=0, required=False)
    total_building_area_sqm = forms.DecimalField(max_digits=10, decimal_places=2, min_value=ZERO, required=False, label="Total property area sqm")
    remove_photo = forms.BooleanField(required=False, label="Remove current photo")

    def __init__(self, *args, **kwargs):
        self.property_obj = kwargs.get("instance")
        initial = kwargs.pop("initial", {}).copy()
        if self.property_obj:
            administration = getattr(self.property_obj, "administration", None)
            initial.update(
                {
                    "construction_year": administration.construction_year if administration else None,
                    "total_building_area_sqm": administration.total_building_area_sqm if administration else None,
                }
            )
        kwargs["initial"] = initial
        super().__init__(*args, **kwargs)
        self.fields["photo"].label = "Upload replacement photo"
        self.fields["photo"].required = False
        self.fields["photo"].help_text = "Optional. Choose a new image to replace the current property photo."

    class Meta:
        model = Property
        fields = ["name", "object_type", "street_address", "postal_code", "city", "photo", "notes"]
        widgets = {
            "photo": forms.FileInput(),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "street_address": "Street / house number",
            "postal_code": "ZIP",
            "city": "City",
        }

    def save(self, commit=True):
        with transaction.atomic():
            property_obj = super().save(commit=False)
            property_obj.address = _format_property_address(property_obj.street_address, property_obj.postal_code, property_obj.city)
            if commit:
                property_obj.save()
            if commit:
                if self.cleaned_data.get("remove_photo") and property_obj.photo:
                    property_obj.photo.delete(save=False)
                    property_obj.photo = ""
                    property_obj.save(update_fields=["photo", "updated_at"])
                PropertyAdministration.objects.update_or_create(
                    property=property_obj,
                    defaults={
                        "construction_year": self.cleaned_data["construction_year"],
                        "total_building_area_sqm": self.cleaned_data["total_building_area_sqm"],
                    },
                )
            return property_obj


class UnitForm(forms.ModelForm):
    def __init__(self, *args, property_obj=None, **kwargs):
        initial = kwargs.pop("initial", {}).copy()
        if property_obj:
            initial.setdefault("property", property_obj)
        kwargs["initial"] = initial
        super().__init__(*args, **kwargs)
        self.fields["area_sqm"].label = "Living area sqm"

    class Meta:
        model = Unit
        fields = ["property", "label", "floor", "area_sqm", "notes"]


class UnitCurrentInfoForm(forms.Form):
    label = forms.CharField(max_length=120, label="Unit name")
    floor = forms.CharField(max_length=40, required=False)
    area_sqm = forms.DecimalField(max_digits=8, decimal_places=2, min_value=ZERO, required=False, label="Living area sqm")
    unit_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), label="Unit notes")

    heating_type = forms.CharField(max_length=160, required=False)
    boiler_installation_info = forms.CharField(max_length=160, required=False, label="Boiler / Therme info")
    instant_water_heater_info = forms.CharField(max_length=160, required=False)
    technical_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    rent_effective_start = FlexibleDateField(required=False, label="Rent valid from")
    cold_rent = forms.DecimalField(max_digits=10, decimal_places=2, min_value=ZERO, required=False, widget=CurrencyInput(), label="Cold rent")
    utility_prepayment = forms.DecimalField(max_digits=10, decimal_places=2, min_value=ZERO, required=False, widget=CurrencyInput(), label="Utilities / prepayments")
    total_rent = forms.DecimalField(max_digits=10, decimal_places=2, min_value=ZERO, required=False, widget=CurrencyInput(), label="Total rent")
    rent_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), label="Rent notes")

    def __init__(self, *args, unit=None, active_lease=None, current_rent_period=None, **kwargs):
        self.unit = unit
        self.active_lease = active_lease
        self.current_rent_period = current_rent_period
        initial = kwargs.pop("initial", {}).copy()
        if unit:
            technical_info = getattr(unit, "technical_info", None)
            initial.update(
                {
                    "label": unit.label,
                    "floor": unit.floor,
                    "area_sqm": unit.area_sqm,
                    "unit_notes": unit.notes,
                    "heating_type": technical_info.heating_type if technical_info else "",
                    "boiler_installation_info": technical_info.boiler_installation_info if technical_info else "",
                    "instant_water_heater_info": technical_info.instant_water_heater_info if technical_info else "",
                    "technical_notes": technical_info.notes if technical_info else "",
                }
            )
        if current_rent_period:
            initial.update(
                {
                    "rent_effective_start": current_rent_period.effective_start,
                    "cold_rent": current_rent_period.cold_rent,
                    "utility_prepayment": current_rent_period.utility_prepayment,
                    "total_rent": current_rent_period.total_rent,
                    "rent_notes": current_rent_period.notes,
                }
            )
        kwargs["initial"] = initial
        super().__init__(*args, **kwargs)
        if not active_lease:
            for field_name in ("rent_effective_start", "cold_rent", "utility_prepayment", "total_rent", "rent_notes"):
                self.fields[field_name].disabled = True
                self.fields[field_name].help_text = "Add a tenant before storing rent."

    def clean(self):
        cleaned = super().clean()
        if not self.active_lease:
            return cleaned
        effective_start = cleaned.get("rent_effective_start")
        cold_rent = cleaned.get("cold_rent")
        utility_prepayment = cleaned.get("utility_prepayment")
        if not effective_start:
            self.add_error("rent_effective_start", "Enter the date this rent is valid from.")
        if cold_rent is None:
            self.add_error("cold_rent", "Enter the monthly cold rent.")
        if utility_prepayment is None:
            self.add_error("utility_prepayment", "Enter the monthly utilities/prepayments.")
        if cold_rent is not None and utility_prepayment is not None and cleaned.get("total_rent") is None:
            cleaned["total_rent"] = _money(cold_rent) + _money(utility_prepayment)
        if effective_start:
            if effective_start < self.active_lease.start_date:
                self.add_error("rent_effective_start", "Rent cannot start before the tenant period starts.")
            if self.active_lease.end_date and effective_start > self.active_lease.end_date:
                self.add_error("rent_effective_start", "Rent cannot start after the tenant period ends.")
            if self.current_rent_period and effective_start < self.current_rent_period.effective_start:
                self.add_error("rent_effective_start", "Use the history correction menu to edit older rent records.")
            same_day = self.active_lease.rent_periods.filter(effective_start=effective_start)
            if self.current_rent_period:
                same_day = same_day.exclude(pk=self.current_rent_period.pk)
            if same_day.exists():
                self.add_error("rent_effective_start", "A rent period already starts on this date. Edit that history row instead.")
        return cleaned

    def save(self):
        with transaction.atomic():
            self.unit.label = self.cleaned_data["label"]
            self.unit.floor = self.cleaned_data["floor"]
            self.unit.area_sqm = self.cleaned_data["area_sqm"]
            self.unit.notes = self.cleaned_data["unit_notes"]
            self.unit.save(update_fields=["label", "floor", "area_sqm", "notes", "updated_at"])
            UnitTechnicalInfo.objects.update_or_create(
                unit=self.unit,
                defaults={
                    "heating_type": self.cleaned_data["heating_type"],
                    "boiler_installation_info": self.cleaned_data["boiler_installation_info"],
                    "instant_water_heater_info": self.cleaned_data["instant_water_heater_info"],
                    "notes": self.cleaned_data["technical_notes"],
                },
            )
            if self.active_lease:
                effective_start = self.cleaned_data["rent_effective_start"]
                rent_defaults = {
                    "cold_rent": self.cleaned_data["cold_rent"],
                    "utility_prepayment": self.cleaned_data["utility_prepayment"],
                    "total_rent": self.cleaned_data["total_rent"],
                    "notes": self.cleaned_data["rent_notes"],
                }
                if self.current_rent_period and self.current_rent_period.effective_start == effective_start:
                    for field_name, value in rent_defaults.items():
                        setattr(self.current_rent_period, field_name, value)
                    self.current_rent_period.save()
                else:
                    _close_overlapping_rent_periods(self.active_lease, effective_start)
                    RentPeriod.objects.create(lease=self.active_lease, effective_start=effective_start, **rent_defaults)
            return self.unit


class TenantForm(forms.ModelForm):
    birthday = FlexibleDateField(required=False)

    class Meta:
        model = Tenant
        fields = [
            "first_name",
            "last_name",
            "email",
            "phone",
            "support_office_name",
            "support_office_email",
            "support_office_phone",
            "birthday",
            "relationship_notes",
            "notes",
        ]


class LeaseForm(forms.ModelForm):
    start_date = FlexibleDateField()
    end_date = FlexibleDateField(required=False)

    def __init__(self, *args, property_obj=None, unit=None, **kwargs):
        initial = kwargs.pop("initial", {}).copy()
        if unit:
            initial.setdefault("unit", unit)
        kwargs["initial"] = initial
        super().__init__(*args, **kwargs)
        if property_obj:
            self.fields["unit"].queryset = Unit.objects.filter(property=property_obj)
        self.fields["start_date"].help_text = "Use DD.MM.YYYY."
        self.fields["end_date"].help_text = "Optional. Use DD.MM.YYYY."

    class Meta:
        model = Lease
        fields = ["unit", "tenant", "start_date", "end_date", "is_active", "notes"]

    def save(self, commit=True):
        with transaction.atomic():
            lease = super().save(commit=commit)
            if commit:
                sync_lease_start_from_rent_periods(lease)
                ensure_primary_lease_person(lease)
                sync_lease_people_dates(lease)
            return lease


class RentPeriodForm(forms.ModelForm):
    effective_start = FlexibleDateField(label="Effective start")
    effective_end = FlexibleDateField(required=False, label="Effective end")

    def __init__(self, *args, property_obj=None, lease=None, **kwargs):
        initial = kwargs.pop("initial", {}).copy()
        if lease:
            initial.setdefault("lease", lease)
        kwargs["initial"] = initial
        super().__init__(*args, **kwargs)
        if property_obj:
            self.fields["lease"].queryset = Lease.objects.filter(unit__property=property_obj).select_related("unit", "tenant")
        self.fields["cold_rent"].label = "Cold rent"
        self.fields["cold_rent"].help_text = "Monthly cold rent for this period."
        self.fields["utility_prepayment"].label = "Utilities / prepayments"
        self.fields["utility_prepayment"].help_text = "Monthly utilities or tenant prepayments."
        self.fields["total_rent"].label = "Total rent"
        self.fields["total_rent"].required = False
        self.fields["total_rent"].help_text = "Optional. Leave blank to use cold rent + utilities."
        self.fields["effective_start"].help_text = "Use DD.MM.YYYY."
        self.fields["effective_end"].help_text = "Optional. Leave blank until the next rent change."

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("total_rent"):
            cleaned["total_rent"] = _money(cleaned.get("cold_rent")) + _money(cleaned.get("utility_prepayment"))
        return cleaned

    def save(self, commit=True):
        with transaction.atomic():
            rent_period = super().save(commit=commit)
            if commit:
                sync_lease_start_from_rent_periods(rent_period.lease)
            return rent_period

    class Meta:
        model = RentPeriod
        fields = ["lease", "effective_start", "effective_end", "cold_rent", "utility_prepayment", "total_rent", "notes"]
        widgets = {
            "cold_rent": CurrencyInput(),
            "utility_prepayment": CurrencyInput(),
            "total_rent": CurrencyInput(),
        }


def _property_tenant_queryset(property_obj):
    if not property_obj:
        return Tenant.objects.none()
    return Tenant.objects.filter(leases__unit__property=property_obj).distinct().order_by("last_name", "first_name")


def _property_person_queryset(property_obj):
    if not property_obj:
        return Tenant.objects.none()
    return (
        Tenant.objects.filter(Q(leases__unit__property=property_obj) | Q(lease_links__lease__unit__property=property_obj))
        .distinct()
        .order_by("last_name", "first_name")
    )


def _close_overlapping_rent_periods(lease, effective_start, exclude_pk=None):
    end_date = effective_start - timedelta(days=1)
    periods = lease.rent_periods.filter(effective_start__lt=effective_start).filter(
        Q(effective_end__isnull=True) | Q(effective_end__gte=effective_start)
    )
    if exclude_pk:
        periods = periods.exclude(pk=exclude_pk)
    periods.update(effective_end=end_date)


def sync_lease_start_from_rent_periods(lease):
    earliest_rent_start = lease.rent_periods.order_by("effective_start").values_list("effective_start", flat=True).first()
    if earliest_rent_start and lease.start_date != earliest_rent_start:
        previous_start = lease.start_date
        lease.start_date = earliest_rent_start
        lease.save(update_fields=["start_date"])
        sync_lease_people_dates(lease, previous_start=previous_start)


def sync_lease_people_dates(lease, previous_start=None):
    people = lease.people.all()
    if previous_start:
        people.filter(move_in_date=previous_start).update(move_in_date=lease.start_date)
    people.filter(move_in_date__lt=lease.start_date).update(move_in_date=lease.start_date)
    if lease.end_date:
        people.filter(Q(move_out_date__isnull=True) | Q(move_out_date__gt=lease.end_date)).update(move_out_date=lease.end_date)


def ensure_primary_lease_person(lease, person=None):
    person = person or lease.tenant
    return LeasePerson.objects.get_or_create(
        lease=lease,
        person=person,
        role=LeasePerson.PRIMARY,
        defaults={
            "move_in_date": lease.start_date,
            "move_out_date": lease.end_date,
            "is_contract_signer": True,
        },
    )[0]


class UnitWithTenantForm(forms.Form):
    TENANT_NEW = "new"
    TENANT_EXISTING = "existing"
    TENANT_VACANT = "vacant"

    property = forms.ModelChoiceField(queryset=Property.objects.all(), widget=forms.HiddenInput())
    label = forms.CharField(max_length=120, label="Unit name")
    floor = forms.CharField(max_length=40, required=False)
    area_sqm = forms.DecimalField(max_digits=8, decimal_places=2, min_value=ZERO, required=False, label="Living area sqm")
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), label="Unit notes")
    tenant_mode = forms.ChoiceField(
        choices=[(TENANT_NEW, "New tenant"), (TENANT_EXISTING, "Existing tenant"), (TENANT_VACANT, "Vacant unit")],
        initial=TENANT_NEW,
        help_text="Use Vacant unit when the apartment exists but has no active tenant yet.",
    )
    existing_tenant = forms.ModelChoiceField(queryset=Tenant.objects.none(), required=False)
    first_name = forms.CharField(max_length=120, required=False)
    last_name = forms.CharField(max_length=120, required=False)
    email = forms.EmailField(required=False)
    phone = forms.CharField(max_length=80, required=False)
    tenant_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), label="Tenant notes")
    lease_start_date = FlexibleDateField(required=False, label="Lease start date", help_text="Use DD.MM.YYYY.")
    cold_rent = forms.DecimalField(max_digits=10, decimal_places=2, min_value=ZERO, required=False, widget=CurrencyInput(), help_text="Monthly cold rent.")
    utility_prepayment = forms.DecimalField(max_digits=10, decimal_places=2, min_value=ZERO, required=False, widget=CurrencyInput(), label="Utilities / prepayments", help_text="Monthly utilities or tenant prepayments.")
    total_rent = forms.DecimalField(max_digits=10, decimal_places=2, min_value=ZERO, required=False, widget=CurrencyInput(), help_text="Optional. Leave blank to use cold rent + utilities.")
    heating_type = forms.CharField(max_length=160, required=False)
    boiler_installation_info = forms.CharField(max_length=160, required=False, label="Boiler info")
    cellar_number = forms.CharField(max_length=80, required=False)
    local_court = forms.CharField(max_length=160, required=False)
    land_register_district = forms.CharField(max_length=160, required=False, label="Land registry")
    sheet_number = forms.CharField(max_length=80, required=False)
    plot_numbers = forms.CharField(max_length=160, required=False)
    management_contact_name = forms.CharField(max_length=160, required=False, label="Management contact")
    management_contact_email = forms.EmailField(required=False)
    management_contact_phone = forms.CharField(max_length=80, required=False)

    def __init__(self, *args, property_obj=None, **kwargs):
        self.property_obj = property_obj
        initial = kwargs.pop("initial", {}).copy()
        if property_obj:
            initial.setdefault("property", property_obj.pk)
        kwargs["initial"] = initial
        super().__init__(*args, **kwargs)
        self.fields["existing_tenant"].queryset = _property_tenant_queryset(property_obj)

    def clean(self):
        cleaned = super().clean()
        tenant_mode = cleaned.get("tenant_mode")
        property_obj = cleaned.get("property")
        label = cleaned.get("label")
        if property_obj and label and Unit.objects.filter(property=property_obj, label=label).exists():
            self.add_error("label", "This property already has a unit with this name.")
        if tenant_mode == self.TENANT_VACANT:
            return cleaned
        if tenant_mode == self.TENANT_EXISTING and not cleaned.get("existing_tenant"):
            self.add_error("existing_tenant", "Choose an existing tenant.")
        if tenant_mode == self.TENANT_NEW and not cleaned.get("last_name"):
            self.add_error("last_name", "Enter the tenant name.")
        if not cleaned.get("lease_start_date"):
            self.add_error("lease_start_date", "Enter the lease start date.")
        for field_name in ("cold_rent", "utility_prepayment"):
            if cleaned.get(field_name) is None:
                self.add_error(field_name, "Enter a monthly amount. Use 0 if there is no amount.")
        if cleaned.get("total_rent") is None and cleaned.get("cold_rent") is not None and cleaned.get("utility_prepayment") is not None:
            cleaned["total_rent"] = _money(cleaned["cold_rent"]) + _money(cleaned["utility_prepayment"])
        return cleaned

    def save(self):
        with transaction.atomic():
            unit = Unit.objects.create(
                property=self.cleaned_data["property"],
                label=self.cleaned_data["label"],
                floor=self.cleaned_data["floor"],
                area_sqm=self.cleaned_data["area_sqm"],
                notes=self.cleaned_data["notes"],
            )
            UnitAdministration.objects.update_or_create(
                unit=unit,
                defaults={"cellar_number": self.cleaned_data["cellar_number"]},
            )
            UnitTechnicalInfo.objects.update_or_create(
                unit=unit,
                defaults={
                    "heating_type": self.cleaned_data["heating_type"],
                    "boiler_installation_info": self.cleaned_data["boiler_installation_info"],
                },
            )
            UnitLandRegistry.objects.update_or_create(
                unit=unit,
                defaults={
                    "local_court": self.cleaned_data["local_court"],
                    "land_register_district": self.cleaned_data["land_register_district"],
                    "sheet_number": self.cleaned_data["sheet_number"],
                    "plot_numbers": self.cleaned_data["plot_numbers"],
                },
            )
            if self.cleaned_data["management_contact_name"] or self.cleaned_data["management_contact_email"] or self.cleaned_data["management_contact_phone"]:
                contact = Contact.objects.create(
                    contact_type=Contact.PROPERTY_MANAGEMENT,
                    name=self.cleaned_data["management_contact_name"] or "Property management",
                    email=self.cleaned_data["management_contact_email"],
                    phone=self.cleaned_data["management_contact_phone"],
                )
                UnitContact.objects.create(unit=unit, contact=contact, role=UnitContact.PROPERTY_MANAGEMENT)
            if self.cleaned_data["tenant_mode"] == self.TENANT_VACANT:
                return unit
            tenant = self.cleaned_data.get("existing_tenant")
            if self.cleaned_data["tenant_mode"] == self.TENANT_NEW:
                tenant = Tenant.objects.create(
                    first_name=self.cleaned_data["first_name"],
                    last_name=self.cleaned_data["last_name"],
                    email=self.cleaned_data["email"],
                    phone=self.cleaned_data["phone"],
                    notes=self.cleaned_data["tenant_notes"],
                )
            lease = Lease.objects.create(unit=unit, tenant=tenant, start_date=self.cleaned_data["lease_start_date"], is_active=True)
            ensure_primary_lease_person(lease, tenant)
            RentPeriod.objects.create(
                lease=lease,
                effective_start=self.cleaned_data["lease_start_date"],
                cold_rent=self.cleaned_data["cold_rent"],
                utility_prepayment=self.cleaned_data["utility_prepayment"],
                total_rent=self.cleaned_data["total_rent"],
            )
            return unit


class TenantChangeForm(forms.Form):
    TENANT_NEW = "new"
    TENANT_EXISTING = "existing"

    tenant_mode = forms.ChoiceField(choices=[(TENANT_NEW, "New tenant"), (TENANT_EXISTING, "Existing tenant")], initial=TENANT_NEW)
    existing_tenant = forms.ModelChoiceField(queryset=Tenant.objects.none(), required=False)
    first_name = forms.CharField(max_length=120, required=False)
    last_name = forms.CharField(max_length=120, required=False)
    email = forms.EmailField(required=False)
    phone = forms.CharField(max_length=80, required=False)
    tenant_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), label="Tenant notes")
    lease_start_date = FlexibleDateField(label="New lease start date", help_text="Use DD.MM.YYYY.")
    cold_rent = forms.DecimalField(max_digits=10, decimal_places=2, min_value=ZERO, widget=CurrencyInput(), help_text="Monthly cold rent from the new lease start.")
    utility_prepayment = forms.DecimalField(max_digits=10, decimal_places=2, min_value=ZERO, widget=CurrencyInput(), label="Utilities / prepayments")
    total_rent = forms.DecimalField(max_digits=10, decimal_places=2, min_value=ZERO, required=False, widget=CurrencyInput(), help_text="Optional. Leave blank to use cold rent + utilities.")

    def __init__(self, *args, unit=None, **kwargs):
        self.unit = unit
        super().__init__(*args, **kwargs)
        self.fields["existing_tenant"].queryset = _property_tenant_queryset(unit.property if unit else None)

    def clean(self):
        cleaned = super().clean()
        tenant_mode = cleaned.get("tenant_mode")
        start_date = cleaned.get("lease_start_date")
        if tenant_mode == self.TENANT_EXISTING and not cleaned.get("existing_tenant"):
            self.add_error("existing_tenant", "Choose an existing tenant.")
        if tenant_mode == self.TENANT_NEW and not cleaned.get("last_name"):
            self.add_error("last_name", "Enter the tenant name.")
        if start_date and self.unit:
            overlapping = self.unit.leases.filter(start_date__gte=start_date, is_active=True)
            if overlapping.exists():
                self.add_error("lease_start_date", "There is already an active lease on or after this date.")
        if cleaned.get("total_rent") is None and cleaned.get("cold_rent") is not None and cleaned.get("utility_prepayment") is not None:
            cleaned["total_rent"] = _money(cleaned["cold_rent"]) + _money(cleaned["utility_prepayment"])
        return cleaned

    def save(self):
        with transaction.atomic():
            start_date = self.cleaned_data["lease_start_date"]
            previous_end = start_date - timedelta(days=1)
            active_leases = self.unit.leases.filter(is_active=True, start_date__lt=start_date).filter(
                Q(end_date__isnull=True) | Q(end_date__gte=start_date)
            )
            for lease in active_leases:
                lease.end_date = previous_end
                lease.is_active = False
                lease.save(update_fields=["end_date", "is_active"])
                sync_lease_people_dates(lease)
                _close_overlapping_rent_periods(lease, start_date)
            tenant = self.cleaned_data.get("existing_tenant")
            if self.cleaned_data["tenant_mode"] == self.TENANT_NEW:
                tenant = Tenant.objects.create(
                    first_name=self.cleaned_data["first_name"],
                    last_name=self.cleaned_data["last_name"],
                    email=self.cleaned_data["email"],
                    phone=self.cleaned_data["phone"],
                    notes=self.cleaned_data["tenant_notes"],
                )
            lease = Lease.objects.create(unit=self.unit, tenant=tenant, start_date=start_date, is_active=True)
            ensure_primary_lease_person(lease, tenant)
            RentPeriod.objects.create(
                lease=lease,
                effective_start=start_date,
                cold_rent=self.cleaned_data["cold_rent"],
                utility_prepayment=self.cleaned_data["utility_prepayment"],
                total_rent=self.cleaned_data["total_rent"],
            )
            return lease


class RentChangeForm(forms.Form):
    effective_start = FlexibleDateField(label="Effective start", help_text="Use DD.MM.YYYY.")
    cold_rent = forms.DecimalField(max_digits=10, decimal_places=2, min_value=ZERO, widget=CurrencyInput(), help_text="Monthly cold rent from this date.")
    utility_prepayment = forms.DecimalField(max_digits=10, decimal_places=2, min_value=ZERO, widget=CurrencyInput(), label="Utilities / prepayments")
    total_rent = forms.DecimalField(max_digits=10, decimal_places=2, min_value=ZERO, required=False, widget=CurrencyInput(), help_text="Optional. Leave blank to use cold rent + utilities.")
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, lease=None, **kwargs):
        self.lease = lease
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        effective_start = cleaned.get("effective_start")
        if effective_start and self.lease:
            if effective_start < self.lease.start_date:
                self.add_error("effective_start", "Rent cannot start before the lease starts.")
            if self.lease.end_date and effective_start > self.lease.end_date:
                self.add_error("effective_start", "Rent cannot start after the lease ends.")
            same_day = self.lease.rent_periods.filter(effective_start=effective_start)
            if same_day.exists():
                self.add_error("effective_start", "A rent period already starts on this date. Edit that row instead.")
        if cleaned.get("total_rent") is None and cleaned.get("cold_rent") is not None and cleaned.get("utility_prepayment") is not None:
            cleaned["total_rent"] = _money(cleaned["cold_rent"]) + _money(cleaned["utility_prepayment"])
        return cleaned

    def save(self):
        with transaction.atomic():
            _close_overlapping_rent_periods(self.lease, self.cleaned_data["effective_start"])
            return RentPeriod.objects.create(
                lease=self.lease,
                effective_start=self.cleaned_data["effective_start"],
                cold_rent=self.cleaned_data["cold_rent"],
                utility_prepayment=self.cleaned_data["utility_prepayment"],
                total_rent=self.cleaned_data["total_rent"],
                notes=self.cleaned_data["notes"],
            )


class LeasePeopleForm(forms.Form):
    PERSON_NONE = "none"
    PERSON_EXISTING = "existing"
    PERSON_NEW = "new"

    add_person_mode = forms.ChoiceField(
        choices=[(PERSON_NONE, "Do not add a person"), (PERSON_EXISTING, "Existing person"), (PERSON_NEW, "New person")],
        initial=PERSON_NONE,
        required=False,
    )
    existing_person = forms.ModelChoiceField(queryset=Tenant.objects.none(), required=False)
    first_name = forms.CharField(max_length=120, required=False)
    last_name = forms.CharField(max_length=120, required=False)
    email = forms.EmailField(required=False)
    phone = forms.CharField(max_length=80, required=False)
    birthday = FlexibleDateField(required=False)
    relationship_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), label="Relationship / person notes")
    new_role = forms.ChoiceField(choices=LeasePerson.ROLES, initial=LeasePerson.CO_TENANT, label="Role")
    new_move_in_date = FlexibleDateField(required=False, label="Move-in date")
    new_move_out_date = FlexibleDateField(required=False, label="Move-out date")
    new_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), label="Role notes")

    def __init__(self, *args, lease=None, **kwargs):
        self.lease = lease
        self.links = list(lease.people.select_related("person").all()) if lease else []
        super().__init__(*args, **kwargs)
        property_obj = lease.unit.property if lease else None
        self.fields["existing_person"].queryset = _property_person_queryset(property_obj)
        for link in self.links:
            prefix = f"link_{link.pk}"
            self.fields[f"{prefix}_first_name"] = forms.CharField(max_length=120, required=False, initial=link.person.first_name, label="First name")
            self.fields[f"{prefix}_last_name"] = forms.CharField(max_length=120, initial=link.person.last_name, label="Last name")
            self.fields[f"{prefix}_email"] = forms.EmailField(required=False, initial=link.person.email, label="Email")
            self.fields[f"{prefix}_phone"] = forms.CharField(max_length=80, required=False, initial=link.person.phone, label="Phone")
            self.fields[f"{prefix}_birthday"] = FlexibleDateField(required=False, initial=link.person.birthday, label="Birthday")
            self.fields[f"{prefix}_relationship_notes"] = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), initial=link.person.relationship_notes, label="Relationship / person notes")
            self.fields[f"{prefix}_role"] = forms.ChoiceField(choices=LeasePerson.ROLES, initial=link.role, label="Role")
            self.fields[f"{prefix}_move_in_date"] = FlexibleDateField(initial=link.move_in_date, label="Move-in date")
            self.fields[f"{prefix}_move_out_date"] = FlexibleDateField(required=False, initial=link.move_out_date, label="Move-out date")
            self.fields[f"{prefix}_notes"] = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), initial=link.notes, label="Role notes")
            self.fields[f"{prefix}_remove"] = forms.BooleanField(required=False, initial=False, label="Remove")

    def _validate_link_dates(self, move_in, move_out, field_prefix):
        if move_out and move_in and move_out < move_in:
            self.add_error(f"{field_prefix}_move_out_date", "Move-out date must be on or after move-in date.")
        if move_in and self.lease and move_in < self.lease.start_date:
            self.add_error(f"{field_prefix}_move_in_date", "Move-in date cannot be before the lease starts.")
        if move_in and self.lease and self.lease.end_date and move_in > self.lease.end_date:
            self.add_error(f"{field_prefix}_move_in_date", "Move-in date cannot be after the lease ends.")
        if move_out and self.lease and self.lease.end_date and move_out > self.lease.end_date:
            self.add_error(f"{field_prefix}_move_out_date", "Move-out date cannot be after the lease ends.")

    def clean(self):
        cleaned = super().clean()
        contract_count = 0
        seen = set()
        for link in self.links:
            prefix = f"link_{link.pk}"
            if cleaned.get(f"{prefix}_remove"):
                continue
            role = cleaned.get(f"{prefix}_role")
            move_in = cleaned.get(f"{prefix}_move_in_date")
            move_out = cleaned.get(f"{prefix}_move_out_date")
            if role in LeasePerson.CONTRACT_ROLES:
                contract_count += 1
            key = (link.person_id, role)
            if key in seen:
                self.add_error(f"{prefix}_role", "This person already has this role for the lease.")
            seen.add(key)
            self._validate_link_dates(move_in, move_out, prefix)

        mode = cleaned.get("add_person_mode")
        new_person = cleaned.get("existing_person")
        if mode == self.PERSON_EXISTING and not new_person:
            self.add_error("existing_person", "Choose an existing person.")
        if mode == self.PERSON_NEW and not cleaned.get("last_name"):
            self.add_error("last_name", "Enter the person's last name.")
        if mode in {self.PERSON_EXISTING, self.PERSON_NEW}:
            role = cleaned.get("new_role")
            if role in LeasePerson.CONTRACT_ROLES:
                contract_count += 1
            move_in = cleaned.get("new_move_in_date") or (self.lease.start_date if self.lease else None)
            move_out = cleaned.get("new_move_out_date")
            cleaned["new_move_in_date"] = move_in
            self._validate_link_dates(move_in, move_out, "new")
            person_id = new_person.pk if new_person else None
            if person_id and (person_id, role) in seen:
                self.add_error("new_role", "This person already has this role for the lease.")

        if contract_count < 1:
            raise forms.ValidationError("A lease must have at least one contract tenant.")
        return cleaned

    @property
    def rows(self):
        rows = []
        for link in self.links:
            prefix = f"link_{link.pk}"
            rows.append(
                {
                    "link": link,
                    "first_name": self[f"{prefix}_first_name"],
                    "last_name": self[f"{prefix}_last_name"],
                    "email": self[f"{prefix}_email"],
                    "phone": self[f"{prefix}_phone"],
                    "birthday": self[f"{prefix}_birthday"],
                    "relationship_notes": self[f"{prefix}_relationship_notes"],
                    "role": self[f"{prefix}_role"],
                    "move_in_date": self[f"{prefix}_move_in_date"],
                    "move_out_date": self[f"{prefix}_move_out_date"],
                    "notes": self[f"{prefix}_notes"],
                    "remove": self[f"{prefix}_remove"],
                }
            )
        return rows

    def save(self):
        with transaction.atomic():
            for link in self.links:
                prefix = f"link_{link.pk}"
                if self.cleaned_data.get(f"{prefix}_remove"):
                    link.delete()
                    continue
                person = link.person
                person.first_name = self.cleaned_data[f"{prefix}_first_name"]
                person.last_name = self.cleaned_data[f"{prefix}_last_name"]
                person.email = self.cleaned_data[f"{prefix}_email"]
                person.phone = self.cleaned_data[f"{prefix}_phone"]
                person.birthday = self.cleaned_data[f"{prefix}_birthday"]
                person.relationship_notes = self.cleaned_data[f"{prefix}_relationship_notes"]
                person.save(update_fields=["first_name", "last_name", "email", "phone", "birthday", "relationship_notes", "updated_at"])
                link.role = self.cleaned_data[f"{prefix}_role"]
                link.move_in_date = self.cleaned_data[f"{prefix}_move_in_date"]
                link.move_out_date = self.cleaned_data[f"{prefix}_move_out_date"]
                link.is_contract_signer = link.role in LeasePerson.CONTRACT_ROLES
                link.notes = self.cleaned_data[f"{prefix}_notes"]
                link.save()

            mode = self.cleaned_data.get("add_person_mode")
            if mode == self.PERSON_NEW:
                person = Tenant.objects.create(
                    first_name=self.cleaned_data["first_name"],
                    last_name=self.cleaned_data["last_name"],
                    email=self.cleaned_data["email"],
                    phone=self.cleaned_data["phone"],
                    birthday=self.cleaned_data["birthday"],
                    relationship_notes=self.cleaned_data["relationship_notes"],
                )
            elif mode == self.PERSON_EXISTING:
                person = self.cleaned_data["existing_person"]
            else:
                person = None
            if person:
                LeasePerson.objects.create(
                    lease=self.lease,
                    person=person,
                    role=self.cleaned_data["new_role"],
                    move_in_date=self.cleaned_data["new_move_in_date"],
                    move_out_date=self.cleaned_data["new_move_out_date"],
                    is_contract_signer=self.cleaned_data["new_role"] in LeasePerson.CONTRACT_ROLES,
                    notes=self.cleaned_data["new_notes"],
                )
            primary_person = (
                self.lease.people.filter(role=LeasePerson.PRIMARY)
                .select_related("person")
                .order_by("person__last_name", "person__first_name")
                .first()
            )
            contract_person = primary_person or (
                self.lease.people.filter(role=LeasePerson.CO_TENANT)
                .select_related("person")
                .order_by("person__last_name", "person__first_name")
                .first()
            )
            if contract_person and self.lease.tenant_id != contract_person.person_id:
                self.lease.tenant = contract_person.person
                self.lease.save(update_fields=["tenant", "updated_at"])
            return self.lease


class UnitAdministrationForm(forms.Form):
    CONTACT_NONE = "none"
    CONTACT_EXISTING = "existing"
    CONTACT_NEW = "new"

    postal_code = forms.CharField(max_length=20, required=False, label="Postal code")
    construction_year = forms.IntegerField(min_value=0, required=False)
    total_building_area_sqm = forms.DecimalField(max_digits=10, decimal_places=2, min_value=ZERO, required=False, label="Total property area sqm")
    property_admin_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), label="Building notes")

    apartment_number = forms.CharField(max_length=80, required=False)
    cellar_number = forms.CharField(max_length=80, required=False)
    ownership_share_text = forms.CharField(max_length=120, required=False, label="Ownership share / MEA")
    monthly_house_fee = forms.DecimalField(max_digits=10, decimal_places=2, min_value=ZERO, required=False, widget=CurrencyInput(), label="Monthly house fee")
    unit_admin_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), label="Unit administration notes")

    local_court = forms.CharField(max_length=160, required=False)
    land_register_district = forms.CharField(max_length=160, required=False)
    sheet_number = forms.CharField(max_length=80, required=False)
    cadastral_district = forms.CharField(max_length=80, required=False, label="Cadastral district / Flur")
    plot_numbers = forms.CharField(max_length=160, required=False)
    land_registry_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    heating_type = forms.CharField(max_length=160, required=False)
    boiler_installation_info = forms.CharField(max_length=160, required=False, label="Boiler / Therme info")
    instant_water_heater_info = forms.CharField(max_length=160, required=False)
    technical_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    contact_mode = forms.ChoiceField(
        choices=[(CONTACT_NONE, "No contact"), (CONTACT_EXISTING, "Existing contact"), (CONTACT_NEW, "New contact")],
        initial=CONTACT_NONE,
        label="Property management contact",
    )
    existing_contact = forms.ModelChoiceField(queryset=Contact.objects.none(), required=False)
    contact_name = forms.CharField(max_length=160, required=False)
    contact_email = forms.EmailField(required=False)
    contact_phone = forms.CharField(max_length=80, required=False)
    contact_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, unit=None, **kwargs):
        self.unit = unit
        initial = kwargs.pop("initial", {}).copy()
        if unit:
            property_admin = getattr(unit.property, "administration", None)
            unit_admin = getattr(unit, "administration", None)
            land_registry = getattr(unit, "land_registry", None)
            technical_info = getattr(unit, "technical_info", None)
            contact_link = unit.contacts.select_related("contact").filter(role=UnitContact.PROPERTY_MANAGEMENT).first()
            initial.update(
                {
                    "postal_code": property_admin.postal_code if property_admin else "",
                    "construction_year": property_admin.construction_year if property_admin else None,
                    "total_building_area_sqm": property_admin.total_building_area_sqm if property_admin else None,
                    "property_admin_notes": property_admin.notes if property_admin else "",
                    "apartment_number": unit_admin.apartment_number if unit_admin else "",
                    "cellar_number": unit_admin.cellar_number if unit_admin else "",
                    "ownership_share_text": unit_admin.ownership_share_text if unit_admin else "",
                    "monthly_house_fee": unit_admin.monthly_house_fee if unit_admin else None,
                    "unit_admin_notes": unit_admin.notes if unit_admin else "",
                    "local_court": land_registry.local_court if land_registry else "",
                    "land_register_district": land_registry.land_register_district if land_registry else "",
                    "sheet_number": land_registry.sheet_number if land_registry else "",
                    "cadastral_district": land_registry.cadastral_district if land_registry else "",
                    "plot_numbers": land_registry.plot_numbers if land_registry else "",
                    "land_registry_notes": land_registry.notes if land_registry else "",
                    "heating_type": technical_info.heating_type if technical_info else "",
                    "boiler_installation_info": technical_info.boiler_installation_info if technical_info else "",
                    "instant_water_heater_info": technical_info.instant_water_heater_info if technical_info else "",
                    "technical_notes": technical_info.notes if technical_info else "",
                    "contact_mode": self.CONTACT_EXISTING if contact_link else self.CONTACT_NONE,
                    "existing_contact": contact_link.contact_id if contact_link else None,
                }
            )
        kwargs["initial"] = initial
        super().__init__(*args, **kwargs)
        self.fields["existing_contact"].queryset = Contact.objects.order_by("name")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("contact_mode") == self.CONTACT_EXISTING and not cleaned.get("existing_contact"):
            self.add_error("existing_contact", "Choose a contact.")
        if cleaned.get("contact_mode") == self.CONTACT_NEW and not cleaned.get("contact_name"):
            self.add_error("contact_name", "Enter the contact name.")
        return cleaned

    def save(self):
        with transaction.atomic():
            PropertyAdministration.objects.update_or_create(
                property=self.unit.property,
                defaults={
                    "postal_code": self.cleaned_data["postal_code"],
                    "construction_year": self.cleaned_data["construction_year"],
                    "total_building_area_sqm": self.cleaned_data["total_building_area_sqm"],
                    "notes": self.cleaned_data["property_admin_notes"],
                },
            )
            UnitAdministration.objects.update_or_create(
                unit=self.unit,
                defaults={
                    "apartment_number": self.cleaned_data["apartment_number"],
                    "cellar_number": self.cleaned_data["cellar_number"],
                    "ownership_share_text": self.cleaned_data["ownership_share_text"],
                    "monthly_house_fee": self.cleaned_data["monthly_house_fee"],
                    "notes": self.cleaned_data["unit_admin_notes"],
                },
            )
            UnitLandRegistry.objects.update_or_create(
                unit=self.unit,
                defaults={
                    "local_court": self.cleaned_data["local_court"],
                    "land_register_district": self.cleaned_data["land_register_district"],
                    "sheet_number": self.cleaned_data["sheet_number"],
                    "cadastral_district": self.cleaned_data["cadastral_district"],
                    "plot_numbers": self.cleaned_data["plot_numbers"],
                    "notes": self.cleaned_data["land_registry_notes"],
                },
            )
            UnitTechnicalInfo.objects.update_or_create(
                unit=self.unit,
                defaults={
                    "heating_type": self.cleaned_data["heating_type"],
                    "boiler_installation_info": self.cleaned_data["boiler_installation_info"],
                    "instant_water_heater_info": self.cleaned_data["instant_water_heater_info"],
                    "notes": self.cleaned_data["technical_notes"],
                },
            )

            self.unit.contacts.filter(role=UnitContact.PROPERTY_MANAGEMENT).delete()
            contact = None
            if self.cleaned_data["contact_mode"] == self.CONTACT_EXISTING:
                contact = self.cleaned_data["existing_contact"]
            elif self.cleaned_data["contact_mode"] == self.CONTACT_NEW:
                contact = Contact.objects.create(
                    contact_type=Contact.PROPERTY_MANAGEMENT,
                    name=self.cleaned_data["contact_name"],
                    email=self.cleaned_data["contact_email"],
                    phone=self.cleaned_data["contact_phone"],
                    notes=self.cleaned_data["contact_notes"],
                )
            if contact:
                UnitContact.objects.create(unit=self.unit, contact=contact, role=UnitContact.PROPERTY_MANAGEMENT)
        return self.unit


class AnnualPropertySnapshotForm(forms.ModelForm):
    class Meta:
        model = AnnualPropertySnapshot
        fields = ["property", "year", "property_value", "vacancy_loss", "manual_rent_adjustment", "valuation_source", "notes"]
        widgets = {
            "property_value": CurrencyInput(),
            "vacancy_loss": CurrencyInput(),
            "manual_rent_adjustment": forms.NumberInput(attrs={"step": "0.01"}),
        }


class AnnualPropertyCostForm(forms.ModelForm):
    class Meta:
        model = AnnualPropertyCost
        fields = ["snapshot", "category", "amount", "notes"]
        widgets = {"amount": CurrencyInput()}


class PotentialDealForm(forms.ModelForm):
    class Meta:
        model = PotentialDeal
        fields = [
            "name",
            "address",
            "status",
            "purchase_price",
            "ownership_share",
            "expected_monthly_cold_rent",
            "expected_monthly_utility_prepayment",
            "yearly_non_recoverable_costs",
            "buying_costs",
            "minimum_dscr",
            "maximum_ltv",
            "notes",
        ]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 2}),
            "purchase_price": CurrencyInput(),
            "ownership_share": forms.NumberInput(attrs={"step": "0.000001", "min": "0", "max": "1"}),
            "expected_monthly_cold_rent": CurrencyInput(),
            "expected_monthly_utility_prepayment": CurrencyInput(),
            "yearly_non_recoverable_costs": CurrencyInput(),
            "buying_costs": CurrencyInput(),
            "maximum_ltv": forms.NumberInput(attrs={"step": "0.000001", "min": "0", "max": "1"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
        help_texts = {
            "purchase_price": "Full-property purchase price.",
            "ownership_share": "Your ownership share as a decimal, e.g. 0.5 for 50%.",
            "expected_monthly_cold_rent": "Full-property expected monthly cold rent.",
            "expected_monthly_utility_prepayment": "Full-property expected monthly utilities/prepayments.",
            "yearly_non_recoverable_costs": "Full-property yearly costs not paid by tenants. Leave empty to use 5% of annual cold rent.",
            "buying_costs": "Full-property buying costs such as notary, taxes, broker, or closing costs.",
            "minimum_dscr": "Optional target DSCR threshold for decision notes.",
            "maximum_ltv": "Optional maximum LTV as a decimal, e.g. 0.8 for 80%.",
        }
        labels = {
            "minimum_dscr": "Minimum DSCR",
            "maximum_ltv": "Maximum LTV",
        }

    def clean_buying_costs(self):
        return self.cleaned_data["buying_costs"] or ZERO


class PotentialDealCreateForm(forms.ModelForm):
    owner_cash_out = FlexibleDecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=ZERO,
        widget=DecimalTextInput(attrs={"placeholder": "0.00"}),
        label="Your Cash Invested",
        help_text="Your real cash invested in the first financing scenario. Do not include bank-financed amounts.",
    )
    loan_amount = FlexibleDecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=ZERO,
        widget=DecimalTextInput(attrs={"placeholder": "0.00"}),
        label="Loan amount",
        help_text="Full-property loan amount for the first financing scenario.",
    )
    interest_rate = PercentageRateField(
        label="Interest rate",
        help_text="Enter the annual rate as a percentage, e.g. 2 for 2%. Up to 4 decimals.",
    )
    monthly_payment = FlexibleDecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=ZERO,
        widget=DecimalTextInput(attrs={"placeholder": "0.00"}),
        label="Monthly payment",
        help_text="Full-property monthly payment for the first financing scenario.",
    )

    class Meta:
        model = PotentialDeal
        fields = [
            "name",
            "purchase_price",
            "expected_monthly_cold_rent",
            "expected_monthly_utility_prepayment",
            "yearly_non_recoverable_costs",
            "ownership_share",
            "buying_costs",
            "minimum_dscr",
            "maximum_ltv",
            "notes",
        ]
        widgets = {
            "purchase_price": CurrencyInput(),
            "expected_monthly_cold_rent": CurrencyInput(),
            "expected_monthly_utility_prepayment": CurrencyInput(),
            "yearly_non_recoverable_costs": CurrencyInput(),
            "ownership_share": forms.NumberInput(attrs={"step": "0.000001", "min": "0", "max": "1"}),
            "buying_costs": CurrencyInput(),
            "maximum_ltv": forms.NumberInput(attrs={"step": "0.000001", "min": "0", "max": "1"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
        help_texts = {
            "purchase_price": "Full-property purchase price.",
            "expected_monthly_cold_rent": "Full-property expected monthly cold rent.",
            "expected_monthly_utility_prepayment": "Full-property expected monthly utilities/prepayments.",
            "yearly_non_recoverable_costs": "Full-property yearly costs not paid by tenants. Leave empty to use 5% of annual cold rent.",
            "ownership_share": "Your ownership share as a decimal, e.g. 0.5 for 50%.",
            "buying_costs": "Full-property buying costs such as notary, taxes, broker, or closing costs.",
            "minimum_dscr": "Optional target DSCR threshold for decision notes.",
            "maximum_ltv": "Optional maximum LTV as a decimal, e.g. 0.8 for 80%.",
        }
        labels = {
            "minimum_dscr": "Minimum DSCR",
            "maximum_ltv": "Maximum LTV",
        }

    def clean_buying_costs(self):
        return self.cleaned_data["buying_costs"] or ZERO

    def save(self, commit=True):
        with transaction.atomic():
            deal = super().save(commit=commit)
            if commit:
                PotentialFinancingScenario.objects.create(
                    deal=deal,
                    name="Initial scenario",
                    owner_cash_out=self.cleaned_data["owner_cash_out"],
                    loan_amount=self.cleaned_data["loan_amount"],
                    interest_rate=self.cleaned_data["interest_rate"],
                    monthly_payment=self.cleaned_data["monthly_payment"],
                    is_default=True,
                )
            return deal


class PotentialFinancingScenarioForm(forms.ModelForm):
    owner_cash_out = FlexibleDecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=ZERO,
        widget=DecimalTextInput(attrs={"placeholder": "0.00"}),
        label="Your Cash Invested",
        help_text="Your real cash invested in this financing scenario. Do not include bank-financed amounts.",
    )
    loan_amount = FlexibleDecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=ZERO,
        widget=DecimalTextInput(attrs={"placeholder": "0.00"}),
        label="Full-property loan amount",
        help_text="Full-property loan amount. Your share is calculated from the ownership share.",
    )
    interest_rate = PercentageRateField(
        label="Annual interest rate",
        help_text="Enter the annual rate as a percentage, e.g. 2 for 2%. Up to 4 decimals.",
    )
    monthly_payment = FlexibleDecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=ZERO,
        widget=DecimalTextInput(attrs={"placeholder": "0.00"}),
        label="Monthly payment",
        help_text="Full-property monthly payment. Annual debt service = monthly payment × 12.",
    )

    class Meta:
        model = PotentialFinancingScenario
        fields = ["name", "owner_cash_out", "loan_amount", "interest_rate", "monthly_payment", "maturity_notes", "is_default", "notes"]
        widgets = {
            "maturity_notes": forms.TextInput(),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "owner_cash_out": "Your Cash Invested",
            "loan_amount": "Full-property loan amount",
            "monthly_payment": "Monthly payment",
            "is_default": "Default scenario",
        }
        help_texts = {
            "owner_cash_out": "Your real cash invested in this financing scenario. Do not include bank-financed amounts.",
            "loan_amount": "Full-property loan amount. Your share is calculated from the ownership share.",
            "interest_rate": "Enter the annual rate as a percentage, e.g. 2 for 2%. Up to 4 decimals.",
            "monthly_payment": "Full-property monthly payment. Annual debt service = monthly payment × 12.",
        }

    def __init__(self, *args, deal=None, **kwargs):
        self.deal = deal
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        scenario = super().save(commit=False)
        if self.deal is not None:
            scenario.deal = self.deal
        if commit:
            scenario.save()
            if scenario.is_default:
                PotentialFinancingScenario.objects.filter(deal=scenario.deal).exclude(pk=scenario.pk).update(is_default=False)
        return scenario


class PotentialDealOptimizerForm(forms.Form):
    RATE_OFFSETS = {
        "rate_100": Decimal("0.000000"),
        "rate_80": Decimal("-0.006000"),
        "rate_60": Decimal("-0.010500"),
        "rate_40": Decimal("-0.011500"),
    }

    maximum_cash_out = FlexibleDecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=CENT,
        widget=DecimalTextInput(attrs={"placeholder": "50000.00"}),
        label="Maximum cash invested",
        help_text="Your maximum cash invested for this optimizer run.",
    )
    fixed_buying_costs = FlexibleDecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=ZERO,
        required=False,
        widget=DecimalTextInput(attrs={"placeholder": "0.00"}),
        label="Fixed buying costs",
        help_text="Full-property buying costs such as notary, taxes, broker, or closing costs. These are added to the project cost and paid in cash.",
    )
    maximum_financing_percent = FlexibleDecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=Decimal("40"),
        max_value=Decimal("100"),
        widget=DecimalTextInput(attrs={"placeholder": "100"}),
        label="Maximum financing %",
        help_text="Maximum financing ratio against the purchase price. The optimizer tests 5% steps from 40% up to this cap.",
    )
    maximum_monthly_payment = FlexibleDecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=CENT,
        widget=DecimalTextInput(attrs={"placeholder": "1500.00"}),
        label="Monthly payment",
        help_text="Full-property monthly payment used as the optimizer payment cap. Higher payments can build equity faster, but they reduce Free Cashflow.",
    )
    rate_100 = PercentageRateField(required=False, label="Interest rate at 100% financing")
    rate_80 = PercentageRateField(required=False, label="Interest rate at 80% financing")
    rate_60 = PercentageRateField(required=False, label="Interest rate at 60% financing")
    rate_40 = PercentageRateField(required=False, label="Interest rate at 40% financing")
    scenario_name = forms.CharField(max_length=160, required=False, label="Scenario name")

    def clean_fixed_buying_costs(self):
        return self.cleaned_data["fixed_buying_costs"] or ZERO

    def clean(self):
        cleaned = super().clean()
        rate_fields = ("rate_100", "rate_80", "rate_60", "rate_40")
        entered_rates = {field: cleaned.get(field) for field in rate_fields if cleaned.get(field) is not None}
        if not entered_rates:
            raise forms.ValidationError("Enter at least one interest-rate anchor. Missing anchors are generated automatically.")
        implied_baseline = sum((rate - self.RATE_OFFSETS[field] for field, rate in entered_rates.items()), ZERO) / Decimal(len(entered_rates))
        generated_rate_fields = []
        for field in rate_fields:
            if cleaned.get(field) is None:
                generated = max(implied_baseline + self.RATE_OFFSETS[field], ZERO).quantize(Decimal("0.000001"))
                cleaned[field] = generated
                generated_rate_fields.append(field)
        self.generated_rate_fields = generated_rate_fields
        self.entered_rate_fields = list(entered_rates)
        return cleaned


def _money(value):
    return Decimal(value or 0).quantize(CENT)


PROPERTY_YEARLY_COST_NOTE = "Yearly non-recoverable costs"
MIGRATED_RECURRING_COST_NOTES = (
    "Migrated to property yearly recurring expense",
    "Running costs are stored on the property as yearly recurring expense",
)


def _is_migrated_recurring_cost(cost):
    return (cost.notes or "") in MIGRATED_RECURRING_COST_NOTES


class PropertyHistoryTableForm(forms.Form):
    name = forms.CharField(max_length=160)
    object_type = forms.ChoiceField(choices=[("", "---------")] + Property.OBJECT_TYPES, required=False, label="Object type")
    address = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
    ownership_share = forms.DecimalField(
        max_digits=7,
        decimal_places=6,
        min_value=ZERO,
        max_value=Decimal("1.000000"),
        widget=forms.NumberInput(attrs={"step": "0.000001", "min": "0", "max": "1"}),
        help_text="Your ownership share as a decimal, e.g. 0.5 for 50%.",
    )
    purchase_price = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=ZERO,
        label="Total purchase price",
        widget=CurrencyInput(),
        help_text="Full-property purchase price. Your share is calculated automatically.",
    )
    cash_invested_at_purchase = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=ZERO,
        label="Total cash invested at purchase",
        widget=CurrencyInput(),
        help_text="Full-property cash paid at purchase: down payment, buyer costs, notary, taxes, broker, initial repairs, and similar items.",
    )
    acquisition_date = FlexibleDateField(required=False, help_text="Use DD.MM.YYYY, e.g. 30.11.2021.")
    selected_year = forms.IntegerField(widget=forms.HiddenInput())
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, property_obj=None, selected_year=None, **kwargs):
        self.property_obj = property_obj
        self.rows = []
        self._snapshot_by_year = {snapshot.year: snapshot for snapshot in property_obj.annual_snapshots.prefetch_related("costs")} if property_obj else {}
        initial = kwargs.pop("initial", {}).copy()
        if property_obj:
            initial.update(
                {
                    "name": property_obj.name,
                    "object_type": property_obj.object_type,
                    "address": property_obj.address,
                    "ownership_share": property_obj.ownership_share,
                    "purchase_price": property_obj.purchase_price,
                    "cash_invested_at_purchase": property_obj.cash_invested_at_purchase,
                    "acquisition_date": property_obj.acquisition_date,
                    "notes": property_obj.notes,
                }
            )
        initial["selected_year"] = selected_year or initial.get("selected_year") or date.today().year
        kwargs["initial"] = initial
        super().__init__(*args, **kwargs)
        self._add_history_fields()
        self._calculate_display_rows()

    def _posted_acquisition_year(self):
        acquisition_value = self.data.get(self.add_prefix("acquisition_date")) if self.is_bound else self.initial.get("acquisition_date")
        parsed = parse_flexible_date(acquisition_value)
        if parsed:
            return parsed.year
        if self._snapshot_by_year:
            return min(self._snapshot_by_year)
        return int(self.initial.get("selected_year") or date.today().year)

    def _table_years(self):
        selected_year_value = self.data.get(self.add_prefix("selected_year")) if self.is_bound else self.initial.get("selected_year")
        try:
            selected_year = int(selected_year_value)
        except (TypeError, ValueError):
            selected_year = date.today().year
        start_year = self._posted_acquisition_year()
        if start_year > selected_year:
            return [selected_year]
        return list(range(start_year, selected_year + 1))

    def _previous_property_value(self, year):
        return self.initial.get("purchase_price") or ZERO

    def _default_yearly_cost(self, year):
        if self.property_obj and self.property_obj.recurring_expense_amount is not None:
            return self.property_obj.recurring_expense_amount
        if self.property_obj:
            from .services import annual_rent_totals

            rent = annual_rent_totals(self.property_obj, year)
            return _money(rent.cold_rent * Decimal("0.05"))
        return ZERO

    def _cost_initial(self, snapshot, year):
        if snapshot:
            costs = list(snapshot.costs.all())
            if costs and not all(_is_migrated_recurring_cost(cost) for cost in costs):
                return _money(sum((cost.amount for cost in costs), ZERO))
        return self._default_yearly_cost(year)

    def _add_history_fields(self):
        for year in self._table_years():
            snapshot = self._snapshot_by_year.get(year)
            self.fields[f"property_value_{year}"] = forms.DecimalField(
                max_digits=12,
                decimal_places=2,
                min_value=ZERO,
                label=f"{year} property value",
                widget=CurrencyInput(attrs={"step": "0.01", "min": "0", "class": "property-value-input"}),
                initial=snapshot.property_value if snapshot else self._previous_property_value(year),
            )
            self.fields[f"non_recoverable_costs_{year}"] = forms.DecimalField(
                max_digits=12,
                decimal_places=2,
                min_value=ZERO,
                label=f"{year} non-recoverable costs",
                widget=CurrencyInput(attrs={"step": "0.01", "min": "0", "class": "property-cost-input"}),
                initial=self._cost_initial(snapshot, year),
            )
            self.fields[f"vacancy_loss_{year}"] = forms.DecimalField(
                max_digits=12,
                decimal_places=2,
                min_value=ZERO,
                label=f"{year} vacancy/loss",
                widget=CurrencyInput(attrs={"step": "0.01", "min": "0", "class": "property-vacancy-input"}),
                initial=snapshot.vacancy_loss if snapshot else ZERO,
            )
            self.fields[f"manual_rent_adjustment_{year}"] = forms.DecimalField(
                max_digits=12,
                decimal_places=2,
                label=f"{year} manual rent adjustment",
                widget=forms.NumberInput(attrs={"step": "0.01", "class": "property-rent-adjustment-input"}),
                initial=snapshot.manual_rent_adjustment if snapshot else ZERO,
            )
            self.fields[f"notes_{year}"] = forms.CharField(
                required=False,
                label=f"{year} notes",
                widget=forms.TextInput(attrs={"class": "property-notes-input"}),
                initial=snapshot.notes if snapshot else "",
            )

    def _field_decimal_value(self, field_name):
        try:
            if self.is_bound:
                return _money(self.data.get(self.add_prefix(field_name)) or self.fields[field_name].initial)
            return _money(self.fields[field_name].initial)
        except Exception:
            return ZERO

    def _calculate_display_rows(self):
        self.rows = []
        for year in self._table_years():
            annual_rent = ZERO
            if self.property_obj:
                from .services import annual_rent_totals

                annual_rent = annual_rent_totals(self.property_obj, year).total_rent
            value = self._field_decimal_value(f"property_value_{year}")
            costs = self._field_decimal_value(f"non_recoverable_costs_{year}")
            vacancy = self._field_decimal_value(f"vacancy_loss_{year}")
            rent_adjustment = self._field_decimal_value(f"manual_rent_adjustment_{year}")
            self.rows.append(
                {
                    "year": year,
                    "annual_rent": annual_rent,
                    "estimated_noi": _money(annual_rent + rent_adjustment - vacancy - costs),
                    "property_value": self[f"property_value_{year}"],
                    "non_recoverable_costs": self[f"non_recoverable_costs_{year}"],
                    "vacancy_loss": self[f"vacancy_loss_{year}"],
                    "manual_rent_adjustment": self[f"manual_rent_adjustment_{year}"],
                    "notes": self[f"notes_{year}"],
                }
            )

    def clean(self):
        cleaned = super().clean()
        self._calculate_display_rows()
        return cleaned

    def save(self):
        with transaction.atomic():
            property_obj = self.property_obj or Property()
            property_obj.name = self.cleaned_data["name"]
            property_obj.object_type = self.cleaned_data["object_type"]
            property_obj.address = self.cleaned_data["address"]
            property_obj.ownership_share = self.cleaned_data["ownership_share"]
            property_obj.purchase_price = self.cleaned_data["purchase_price"]
            property_obj.cash_invested_at_purchase = self.cleaned_data["cash_invested_at_purchase"]
            property_obj.acquisition_date = self.cleaned_data["acquisition_date"]
            property_obj.notes = self.cleaned_data["notes"]
            property_obj.save()

            for year in self._table_years():
                snapshot, _ = AnnualPropertySnapshot.objects.update_or_create(
                    property=property_obj,
                    year=year,
                    defaults={
                        "property_value": self.cleaned_data[f"property_value_{year}"],
                        "vacancy_loss": self.cleaned_data[f"vacancy_loss_{year}"],
                        "manual_rent_adjustment": self.cleaned_data[f"manual_rent_adjustment_{year}"],
                        "notes": self.cleaned_data[f"notes_{year}"],
                    },
                )
                snapshot.costs.exclude(category=AnnualPropertyCost.OTHER).delete()
                AnnualPropertyCost.objects.update_or_create(
                    snapshot=snapshot,
                    category=AnnualPropertyCost.OTHER,
                    defaults={"amount": self.cleaned_data[f"non_recoverable_costs_{year}"], "notes": PROPERTY_YEARLY_COST_NOTE},
                )
        self.property_obj = property_obj
        return property_obj


def _active_months(year, start_date, maturity_date):
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    active_start = max(start_date or year_start, year_start)
    active_end = min(maturity_date or year_end, year_end)
    if active_end < active_start:
        return 0
    months = 0
    for month in range(1, 13):
        month_start = date(year, month, 1)
        month_end = date(year, month, monthrange(year, month)[1])
        if month_end >= active_start and month_start <= active_end:
            months += 1
    return months


class LoanBalanceTableForm(forms.Form):
    property = forms.ModelChoiceField(queryset=Property.objects.all())
    name = forms.CharField(max_length=160, label="Loan name")
    original_amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=ZERO,
        label="Total starting loan value",
        widget=CurrencyInput(),
        help_text="Full-property starting loan amount. Your share is calculated from the property's ownership share.",
    )
    start_date = FlexibleDateField(label="Starting date", help_text="Use DD.MM.YYYY, e.g. 30.11.2021.")
    selected_year = forms.IntegerField(widget=forms.HiddenInput())
    default_interest_rate = forms.DecimalField(
        max_digits=7,
        decimal_places=6,
        min_value=ZERO,
        label="Interest rate",
        widget=forms.NumberInput(attrs={"step": "0.000001", "min": "0"}),
        help_text="Loan-level annual rate as decimal, e.g. 0.0157 for 1.57%.",
    )
    default_monthly_payment = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=ZERO,
        label="Total monthly payment",
        widget=CurrencyInput(),
        help_text="Full-property scheduled monthly payment. Extra repayments are calculated from entered closing balances.",
    )
    lender = forms.CharField(max_length=160, required=False)
    maturity_date = FlexibleDateField(required=False, help_text="Optional. Use DD.MM.YYYY.")
    rate_reset_date = FlexibleDateField(required=False, help_text="Optional. Use DD.MM.YYYY.")
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, loan=None, selected_year=None, **kwargs):
        self.loan = loan
        self.rows = []
        self.rate_reset_date = None
        self._snapshot_by_year = {snapshot.year: snapshot for snapshot in loan.annual_snapshots.all()} if loan else {}
        initial = kwargs.pop("initial", {}).copy()
        if loan:
            initial.update(
                {
                    "property": loan.property_id,
                    "name": loan.name,
                    "original_amount": loan.original_amount,
                    "start_date": loan.start_date,
                    "default_interest_rate": loan.default_interest_rate,
                    "default_monthly_payment": loan.default_monthly_payment,
                    "lender": loan.lender,
                    "maturity_date": loan.maturity_date,
                    "notes": loan.notes,
                }
            )
            latest_snapshot = loan.annual_snapshots.order_by("-year").first()
            if latest_snapshot:
                initial.setdefault("rate_reset_date", latest_snapshot.rate_reset_date)
        initial["selected_year"] = selected_year or initial.get("selected_year") or date.today().year
        kwargs["initial"] = initial
        super().__init__(*args, **kwargs)
        self._add_balance_fields()
        if not self.is_bound:
            self._calculate_initial_rows()

    def _posted_start_year(self):
        start_date_value = self.data.get(self.add_prefix("start_date")) if self.is_bound else self.initial.get("start_date")
        parsed = parse_flexible_date(start_date_value)
        if parsed:
            return parsed.year
        return int(self.initial.get("selected_year") or date.today().year)

    def _table_years(self):
        selected_year_value = self.data.get(self.add_prefix("selected_year")) if self.is_bound else self.initial.get("selected_year")
        try:
            selected_year = int(selected_year_value)
        except (TypeError, ValueError):
            selected_year = date.today().year
        maturity_date_value = self.data.get(self.add_prefix("maturity_date")) if self.is_bound else self.initial.get("maturity_date")
        maturity_date = parse_flexible_date(maturity_date_value)
        if maturity_date:
            selected_year = min(selected_year, maturity_date.year)
        start_year = self._posted_start_year()
        if start_year > selected_year:
            return [selected_year]
        return list(range(start_year, selected_year + 1))

    def _add_balance_fields(self):
        for year in self._table_years():
            snapshot = self._snapshot_by_year.get(year)
            initial = snapshot.closing_balance if snapshot else None
            if initial is None:
                previous = self._snapshot_by_year.get(year - 1)
                initial = previous.closing_balance if previous else self.initial.get("original_amount")
            self.fields[f"closing_balance_{year}"] = forms.DecimalField(
                max_digits=12,
                decimal_places=2,
                min_value=ZERO,
                label=f"{year} closing balance",
                widget=CurrencyInput(),
                initial=initial,
                required=False,
            )

    def _calculate_initial_rows(self):
        try:
            property_obj = Property.objects.get(pk=self.initial.get("property"))
            opening = _money(self.initial.get("original_amount"))
            interest_rate = Decimal(self.initial.get("default_interest_rate") or 0)
            monthly_payment = _money(self.initial.get("default_monthly_payment"))
            start_date = self.initial.get("start_date")
            maturity_date = self.initial.get("maturity_date")
            self.rows = []
            for year in self._table_years():
                field = self.fields[f"closing_balance_{year}"]
                closing = _money(field.initial)
                row = self._calculate_row(year, opening, closing, interest_rate, monthly_payment, start_date, maturity_date, property_obj.ownership_share)
                row["field"] = self[f"closing_balance_{year}"]
                self.rows.append(row)
                opening = closing
        except (ArithmeticError, TypeError, ValueError, Property.DoesNotExist):
            self.rows = []

    @staticmethod
    def expected_closing_balance(opening, annual_rate, monthly_payment, active_months):
        balance = _money(opening)
        monthly_rate = (annual_rate or ZERO) / Decimal("12")
        for _ in range(active_months):
            interest = (balance * monthly_rate).quantize(CENT, rounding=ROUND_HALF_UP)
            principal = _money(monthly_payment - interest)
            balance = _money(balance - principal)
        return max(balance, ZERO)

    def _calculate_row(self, year, opening, closing, interest_rate, monthly_payment, start_date, maturity_date, owner_share):
        active_months = _active_months(year, start_date, maturity_date)
        scheduled_payments = _money(monthly_payment * Decimal(active_months))
        expected_closing = self.expected_closing_balance(opening, interest_rate, monthly_payment, active_months)
        extra_repayment = _money(max(expected_closing - closing, ZERO))
        variance = _money(max(closing - expected_closing, ZERO))
        debt_service = _money(scheduled_payments + extra_repayment)
        principal = _money(opening - closing)
        interest = _money(debt_service - principal)
        return {
            "year": year,
            "owner_share": owner_share,
            "active_months": active_months,
            "opening_balance": opening,
            "expected_closing_balance": expected_closing,
            "closing_balance": closing,
            "extra_repayment": extra_repayment,
            "variance": variance,
            "scheduled_payments": scheduled_payments,
            "debt_service": debt_service,
            "principal_paid": principal,
            "interest_paid": interest,
            "effective_interest_rate": (interest / opening).quantize(Decimal("0.0001")) if opening else ZERO,
            "amortization_rate": (principal / opening).quantize(Decimal("0.0001")) if opening else ZERO,
            "owner_closing_balance": _money(closing * owner_share),
        }

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        if cleaned["maturity_date"] and cleaned["maturity_date"] < cleaned["start_date"]:
            self.add_error("maturity_date", "Maturity date must be after the starting date.")
            return cleaned
        opening = _money(cleaned["original_amount"])
        self.rows = []
        for year in self._table_years():
            closing = _money(cleaned.get(f"closing_balance_{year}") or self.fields[f"closing_balance_{year}"].initial)
            if closing > opening:
                self.add_error(f"closing_balance_{year}", "Closing balance cannot exceed opening balance.")
                break
            row = self._calculate_row(
                year,
                opening,
                closing,
                cleaned["default_interest_rate"],
                cleaned["default_monthly_payment"],
                cleaned["start_date"],
                cleaned["maturity_date"],
                cleaned["property"].ownership_share,
            )
            row["field"] = self[f"closing_balance_{year}"]
            if row["active_months"] == 0:
                self.add_error(f"closing_balance_{year}", "The loan is not active in this year.")
            if row["interest_paid"] < 0:
                self.add_error(f"closing_balance_{year}", "Closing balance implies more repayment than scheduled payments plus extra repayment can support.")
            self.rows.append(row)
            opening = closing
        return cleaned

    def save(self):
        loan = self.loan or Loan()
        loan.property = self.cleaned_data["property"]
        loan.name = self.cleaned_data["name"]
        loan.original_amount = self.cleaned_data["original_amount"]
        loan.default_interest_rate = self.cleaned_data["default_interest_rate"]
        loan.default_monthly_payment = self.cleaned_data["default_monthly_payment"]
        loan.start_date = self.cleaned_data["start_date"]
        loan.lender = self.cleaned_data["lender"]
        loan.maturity_date = self.cleaned_data["maturity_date"]
        loan.notes = self.cleaned_data["notes"]
        loan.save()
        for row in self.rows:
            snapshot, _ = AnnualLoanSnapshot.objects.get_or_create(loan=loan, year=row["year"])
            snapshot.opening_balance = row["opening_balance"]
            snapshot.closing_balance = row["closing_balance"]
            snapshot.interest_paid = row["interest_paid"]
            snapshot.principal_paid = row["principal_paid"]
            snapshot.interest_rate = self.cleaned_data["default_interest_rate"]
            snapshot.monthly_payment = self.cleaned_data["default_monthly_payment"]
            snapshot.debt_service = row["debt_service"]
            snapshot.rate_reset_date = self.cleaned_data["rate_reset_date"]
            snapshot.save()
        if self.rows:
            from .services import backfill_property_snapshots

            backfill_property_snapshots(loan.property, through_year=max(row["year"] for row in self.rows))
        self.loan = loan
        return loan, self.rows


class LoanForm(forms.ModelForm):
    start_date = FlexibleDateField(required=False, help_text="Use DD.MM.YYYY.")
    maturity_date = FlexibleDateField(required=False, help_text="Use DD.MM.YYYY.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["original_amount"].label = "Total original loan amount"
        self.fields["original_amount"].help_text = "Full-property loan amount. The app calculates your share from the property's ownership share for ROI and portfolio KPIs."

    class Meta:
        model = Loan
        fields = ["property", "name", "lender", "original_amount", "start_date", "maturity_date", "notes"]
        widgets = {
            "original_amount": CurrencyInput(),
        }


class AnnualLoanSnapshotForm(forms.ModelForm):
    rate_reset_date = FlexibleDateField(required=False, help_text="Use DD.MM.YYYY.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["opening_balance"].label = "Total opening balance"
        self.fields["opening_balance"].help_text = "Full-property loan balance at the start of the year."
        self.fields["closing_balance"].label = "Total closing balance"
        self.fields["closing_balance"].help_text = "Full-property loan balance at the end of the year."
        self.fields["interest_paid"].label = "Total interest paid"
        self.fields["interest_paid"].help_text = "Full-property annual interest paid. Your share is calculated for KPIs."
        self.fields["principal_paid"].label = "Total principal paid"
        self.fields["principal_paid"].help_text = "Full-property annual principal repayment. Your share is calculated for KPIs."
        self.fields["interest_rate"].help_text = "Effective annual interest rate for this loan year."
        self.fields["interest_rate"].label = "Effective interest rate"
        self.fields["monthly_payment"].label = "Total monthly payment"
        self.fields["monthly_payment"].help_text = "Monthly payment for this loan in this year."
        self.fields["debt_service"].label = "Total annual debt service"
        self.fields["debt_service"].required = False
        self.fields["debt_service"].help_text = "Optional full-property annual total. Leave blank to use monthly payment × 12."

    class Meta:
        model = AnnualLoanSnapshot
        fields = [
            "loan",
            "year",
            "opening_balance",
            "closing_balance",
            "interest_paid",
            "principal_paid",
            "interest_rate",
            "monthly_payment",
            "debt_service",
            "rate_reset_date",
            "notes",
        ]
        widgets = {
            "opening_balance": CurrencyInput(),
            "closing_balance": CurrencyInput(),
            "interest_paid": CurrencyInput(),
            "principal_paid": CurrencyInput(),
            "interest_rate": forms.NumberInput(attrs={"step": "0.000001", "min": "0"}),
            "monthly_payment": CurrencyInput(),
            "debt_service": CurrencyInput(),
        }


class WorkbookImportForm(forms.Form):
    workbook = forms.FileField(help_text="Upload Master-Immos.xlsx or another workbook in the same structure.")
    year = forms.IntegerField(min_value=1900, max_value=2200, help_text="Year used for the imported annual snapshots.")


class DatabaseRestoreForm(forms.Form):
    backup_file = forms.FileField(help_text="Upload a SQLite .db backup created by this app.")
    confirm_replace = forms.BooleanField(label="Replace the current database with this backup")
