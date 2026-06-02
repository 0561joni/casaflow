from django.contrib import admin

from .models import (
    AnnualLoanSnapshot,
    AnnualPropertyCost,
    AnnualPropertySnapshot,
    AnnualPortfolioTax,
    AppSettings,
    Contact,
    ImportRun,
    Lease,
    LeasePerson,
    Loan,
    PotentialDeal,
    PotentialFinancingScenario,
    Property,
    PropertyAdministration,
    RentPeriod,
    ReportExport,
    Tenant,
    Unit,
    UnitAdministration,
    UnitContact,
    UnitLandRegistry,
    UnitTechnicalInfo,
)


class UnitInline(admin.TabularInline):
    model = Unit
    extra = 0


class LoanInline(admin.TabularInline):
    model = Loan
    extra = 0


class AnnualPropertyCostInline(admin.TabularInline):
    model = AnnualPropertyCost
    extra = 0


class AnnualLoanSnapshotInline(admin.TabularInline):
    model = AnnualLoanSnapshot
    extra = 0


class PotentialFinancingScenarioInline(admin.TabularInline):
    model = PotentialFinancingScenario
    extra = 0


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ("name", "object_type", "ownership_share", "purchase_price", "cash_invested_at_purchase", "recurring_expense_amount", "acquisition_date")
    search_fields = ("name", "address")
    inlines = [UnitInline, LoanInline]


@admin.register(AnnualPropertySnapshot)
class AnnualPropertySnapshotAdmin(admin.ModelAdmin):
    list_display = ("property", "year", "property_value", "vacancy_loss", "manual_rent_adjustment")
    list_filter = ("year",)
    inlines = [AnnualPropertyCostInline]


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ("name", "property", "lender", "original_amount", "maturity_date")
    list_filter = ("property",)
    inlines = [AnnualLoanSnapshotInline]


@admin.register(PotentialDeal)
class PotentialDealAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "purchase_price", "ownership_share")
    list_filter = ("status",)
    search_fields = ("name", "address")
    inlines = [PotentialFinancingScenarioInline]


admin.site.register(Unit)
admin.site.register(PropertyAdministration)
admin.site.register(UnitAdministration)
admin.site.register(UnitLandRegistry)
admin.site.register(UnitTechnicalInfo)
admin.site.register(Contact)
admin.site.register(UnitContact)
admin.site.register(Tenant)
admin.site.register(Lease)
admin.site.register(LeasePerson)
admin.site.register(RentPeriod)
admin.site.register(AnnualPropertyCost)
admin.site.register(AnnualPortfolioTax)
admin.site.register(AnnualLoanSnapshot)
admin.site.register(ImportRun)
admin.site.register(ReportExport)
admin.site.register(AppSettings)
