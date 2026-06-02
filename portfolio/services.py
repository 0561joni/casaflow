from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from django.db.models import Q, Sum

from .models import AnnualPortfolioTax, AppSettings, AnnualLoanSnapshot, AnnualPropertyCost, AnnualPropertySnapshot, Lease, PotentialDeal, PotentialFinancingScenario, Property, RentPeriod, Unit


ZERO = Decimal("0.00")
CENT = Decimal("0.01")


def money(value: Decimal | int | float | None) -> Decimal:
    return Decimal(value or 0).quantize(CENT, rounding=ROUND_HALF_UP)


def ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
    if not denominator:
        return ZERO
    return (numerator / denominator).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def normalize_tax_mode(tax_mode: str | None) -> str:
    return "before" if tax_mode == "before" else "after"


def estimated_tax_for_result(taxable_result: Decimal, effective_tax_rate: Decimal, loss_benefit_enabled: bool = True) -> Decimal:
    if taxable_result < 0 and not loss_benefit_enabled:
        return ZERO
    return money(taxable_result * effective_tax_rate)


def annual_tax_deductible_costs(year: int) -> Decimal:
    row = AnnualPortfolioTax.objects.filter(year=year).first()
    return money(row.tax_deductible_costs if row else ZERO)


def current_debt_from_annual_snapshot(opening: Decimal, closing: Decimal, year: int, as_of: date | None = None) -> Decimal:
    as_of = as_of or date.today()
    if year < as_of.year:
        return money(closing)
    if year > as_of.year:
        return money(opening)
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    elapsed_days = Decimal((min(max(as_of, year_start), year_end) - year_start).days)
    total_days = Decimal((year_end - year_start).days)
    if total_days <= 0:
        return money(closing)
    return money(opening + ((closing - opening) * (elapsed_days / total_days)))


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])


def _overlap_days(start: date, end: date, window_start: date, window_end: date) -> int:
    overlap_start = max(start, window_start)
    overlap_end = min(end, window_end)
    if overlap_end < overlap_start:
        return 0
    return (overlap_end - overlap_start).days + 1


@dataclass(frozen=True)
class RentTotals:
    cold_rent: Decimal
    utility_prepayment: Decimal
    total_rent: Decimal


def annual_rent_totals(property_obj: Property, year: int) -> RentTotals:
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    periods = RentPeriod.objects.select_related("lease__unit").filter(
        lease__unit__property=property_obj,
        effective_start__lte=year_end,
    ).filter(effective_end__isnull=True) | RentPeriod.objects.select_related("lease__unit").filter(
        lease__unit__property=property_obj,
        effective_start__lte=year_end,
        effective_end__gte=year_start,
    )

    cold = ZERO
    utility = ZERO
    total = ZERO
    for period in periods.distinct():
        period_start = max(period.effective_start, period.lease.start_date)
        period_end = min(period.effective_end or year_end, period.lease.end_date or year_end)
        for month in range(1, 13):
            month_start, month_end = _month_bounds(year, month)
            days = _overlap_days(period_start, period_end, month_start, month_end)
            if not days:
                continue
            month_days = Decimal(monthrange(year, month)[1])
            factor = Decimal(days) / month_days
            cold += period.cold_rent * factor
            utility += period.utility_prepayment * factor
            total += period.total_rent * factor
    return RentTotals(money(cold), money(utility), money(total))


@dataclass(frozen=True)
class UnitRentOverview:
    unit: Unit
    active_lease: Optional[Lease]
    current_rent: Optional[RentPeriod]
    cold_rent: Decimal
    utility_prepayment: Decimal
    total_rent: Decimal
    status: str
    administration_complete: bool


def active_lease_for_unit(unit: Unit, as_of: date | None = None) -> Optional[Lease]:
    as_of = as_of or date.today()
    return (
        unit.leases.select_related("tenant")
        .filter(is_active=True, start_date__lte=as_of)
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=as_of))
        .order_by("-start_date")
        .first()
    )


def current_rent_period_for_lease(lease: Lease | None, as_of: date | None = None) -> Optional[RentPeriod]:
    if lease is None:
        return None
    as_of = as_of or date.today()
    return (
        lease.rent_periods.filter(effective_start__lte=as_of)
        .filter(Q(effective_end__isnull=True) | Q(effective_end__gte=as_of))
        .order_by("-effective_start")
        .first()
    )


def unit_rent_overview(unit: Unit, as_of: date | None = None) -> UnitRentOverview:
    lease = active_lease_for_unit(unit, as_of)
    rent = current_rent_period_for_lease(lease, as_of)
    status = "Active" if lease else "Vacant"
    return UnitRentOverview(
        unit=unit,
        active_lease=lease,
        current_rent=rent,
        cold_rent=money(rent.cold_rent if rent else ZERO),
        utility_prepayment=money(rent.utility_prepayment if rent else ZERO),
        total_rent=money(rent.total_rent if rent else ZERO),
        status=status,
        administration_complete=unit_administration_complete(unit),
    )


def property_unit_overviews(property_obj: Property, as_of: date | None = None) -> list[UnitRentOverview]:
    return [unit_rent_overview(unit, as_of) for unit in property_obj.units.all()]


def unit_administration_complete(unit: Unit) -> bool:
    unit_admin = getattr(unit, "administration", None)
    land_registry = getattr(unit, "land_registry", None)
    technical_info = getattr(unit, "technical_info", None)
    return bool(
        unit_admin
        and unit_admin.apartment_number
        and unit_admin.ownership_share_text
        and unit_admin.monthly_house_fee is not None
        and land_registry
        and land_registry.local_court
        and land_registry.land_register_district
        and land_registry.sheet_number
        and technical_info
        and technical_info.heating_type
    )


@dataclass(frozen=True)
class LoanMetrics:
    opening_balance: Decimal
    closing_balance: Decimal
    interest_paid: Decimal
    principal_paid: Decimal
    debt_service: Decimal
    average_rate: Decimal


@dataclass(frozen=True)
class LoanPerformance:
    snapshot: AnnualLoanSnapshot
    loan: object
    year: int
    opening_balance: Decimal
    closing_balance: Decimal
    current_debt: Decimal
    interest_paid: Decimal
    principal_paid: Decimal
    monthly_payment: Decimal
    debt_service: Decimal
    effective_interest_rate: Decimal
    amortization_rate: Decimal
    interest_share_of_payment: Decimal


def loan_metrics(property_obj: Property, year: int) -> LoanMetrics:
    rows = AnnualLoanSnapshot.objects.filter(loan__property=property_obj, year=year)
    owner_share = property_obj.ownership_share
    aggregates = rows.aggregate(
        opening_balance=Sum("opening_balance"),
        closing_balance=Sum("closing_balance"),
        interest_paid=Sum("interest_paid"),
        principal_paid=Sum("principal_paid"),
        debt_service=Sum("debt_service"),
    )
    opening = money(money(aggregates["opening_balance"]) * owner_share)
    interest = money(money(aggregates["interest_paid"]) * owner_share)
    return LoanMetrics(
        opening_balance=opening,
        closing_balance=money(money(aggregates["closing_balance"]) * owner_share),
        interest_paid=interest,
        principal_paid=money(money(aggregates["principal_paid"]) * owner_share),
        debt_service=money(money(aggregates["debt_service"]) * owner_share),
        average_rate=ratio(interest, opening),
    )


def loan_performance_rows(year: int | None = None) -> list[LoanPerformance]:
    if year is None:
        year = (
            AnnualLoanSnapshot.objects.order_by("-year")
            .values_list("year", flat=True)
            .first()
            or date.today().year
        )
    snapshots = (
        AnnualLoanSnapshot.objects.select_related("loan", "loan__property")
        .filter(year=year)
        .order_by("loan__property__name", "loan__name")
    )
    rows = []
    for snapshot in snapshots:
        owner_share = snapshot.loan.property.ownership_share
        opening = money(snapshot.opening_balance * owner_share)
        closing = money(snapshot.closing_balance * owner_share)
        interest = money(snapshot.interest_paid * owner_share)
        principal = money(snapshot.principal_paid * owner_share)
        debt_service = money(snapshot.debt_service * owner_share)
        rows.append(
            LoanPerformance(
                snapshot=snapshot,
                loan=snapshot.loan,
                year=snapshot.year,
                opening_balance=opening,
                closing_balance=closing,
                current_debt=current_debt_from_annual_snapshot(opening, closing, snapshot.year),
                interest_paid=interest,
                principal_paid=principal,
                monthly_payment=money(snapshot.monthly_payment * owner_share),
                debt_service=debt_service,
                effective_interest_rate=ratio(interest, opening),
                amortization_rate=ratio(principal, opening),
                interest_share_of_payment=ratio(interest, debt_service),
            )
        )
    return rows


@dataclass(frozen=True)
class PropertyPerformance:
    property: Property
    year: int
    property_value: Decimal
    annual_cold_rent: Decimal
    annual_total_rent: Decimal
    operating_costs: Decimal
    recurring_expense: Decimal
    vacancy_loss: Decimal
    noi: Decimal
    debt_service: Decimal
    interest_paid: Decimal
    principal_paid: Decimal
    purchase_cash_out: Decimal
    annual_cash_in: Decimal
    annual_cash_out: Decimal
    cashflow_before_tax: Decimal
    estimated_taxable_result: Decimal
    estimated_tax: Decimal
    cashflow_after_tax: Decimal
    cashflow: Decimal
    free_cashflow_before_tax: Decimal
    free_cashflow_after_tax: Decimal
    free_cashflow: Decimal
    annual_equity_build: Decimal
    annual_owner_roi_before_tax: Optional[Decimal]
    annual_owner_roi_after_tax: Optional[Decimal]
    annual_owner_roi: Optional[Decimal]
    cumulative_cash_in: Decimal
    cumulative_cash_out: Decimal
    cumulative_cashflow_before_tax: Decimal
    cumulative_estimated_tax: Decimal
    cumulative_cashflow_after_tax: Decimal
    cumulative_cashflow: Decimal
    cumulative_free_cashflow_before_tax: Decimal
    cumulative_free_cashflow_after_tax: Decimal
    cumulative_free_cashflow: Decimal
    cumulative_equity_build: Decimal
    cumulative_owner_roi_before_tax: Optional[Decimal]
    cumulative_owner_roi_after_tax: Optional[Decimal]
    cumulative_owner_roi: Optional[Decimal]
    closing_debt: Decimal
    owner_equity_basis: Decimal
    equity_value: Decimal
    gross_yield: Decimal
    net_yield: Decimal
    ltv: Decimal
    cash_equity_roi: Optional[Decimal]
    debt_service_coverage: Decimal


MIGRATED_RECURRING_COST_NOTES = {
    "Migrated to property yearly recurring expense",
    "Running costs are stored on the property as yearly recurring expense",
}


def _is_migrated_recurring_cost(cost: AnnualPropertyCost) -> bool:
    return (cost.notes or "") in MIGRATED_RECURRING_COST_NOTES


def snapshot_operating_costs(snapshot: AnnualPropertySnapshot, annual_cold_rent: Decimal, owner_share: Decimal) -> tuple[Decimal, Decimal]:
    costs = list(snapshot.costs.all())
    if costs and not all(_is_migrated_recurring_cost(cost) for cost in costs):
        amount = money(sum((cost.amount for cost in costs), ZERO) * owner_share)
        return amount, amount
    if snapshot.property.recurring_expense_amount is None:
        amount = money(annual_cold_rent * Decimal("0.05"))
        return amount, amount
    amount = money(snapshot.property.recurring_expense_amount * owner_share)
    return amount, amount


def property_performance(
    snapshot: AnnualPropertySnapshot,
    tax_mode: str = "after",
    tax_settings: AppSettings | None = None,
) -> PropertyPerformance:
    tax_mode = "before"
    property_obj = snapshot.property
    owner_share = property_obj.ownership_share
    rent = annual_rent_totals(property_obj, snapshot.year)
    loan = loan_metrics(property_obj, snapshot.year)
    owner_property_value = money(snapshot.property_value * owner_share)
    annual_cold_rent = money(rent.cold_rent * owner_share)
    costs, recurring_expense = snapshot_operating_costs(snapshot, annual_cold_rent, owner_share)
    annual_total_rent = money(rent.total_rent * owner_share + snapshot.manual_rent_adjustment)
    noi = money(annual_cold_rent - snapshot.vacancy_loss - costs)
    purchase_cash_out = money(property_obj.cash_invested_at_purchase * owner_share)
    annual_cash_in = annual_cold_rent
    annual_cash_out = money(costs + loan.interest_paid + snapshot.vacancy_loss)
    cashflow_before_tax = money(annual_cash_in - annual_cash_out)
    estimated_taxable_result = cashflow_before_tax
    estimated_tax = ZERO
    cashflow_after_tax = cashflow_before_tax
    annual_equity_build = loan.principal_paid
    free_cashflow_before_tax = money(cashflow_before_tax - annual_equity_build)
    free_cashflow_after_tax = money(cashflow_after_tax - annual_equity_build)
    annual_owner_roi_before_tax = None
    annual_owner_roi_after_tax = None
    if purchase_cash_out > 0:
        annual_owner_roi_before_tax = ratio(cashflow_before_tax, purchase_cash_out)
        annual_owner_roi_after_tax = ratio(cashflow_after_tax, purchase_cash_out)
    cashflow = cashflow_after_tax if tax_mode == "after" else cashflow_before_tax
    free_cashflow = free_cashflow_after_tax if tax_mode == "after" else free_cashflow_before_tax
    annual_owner_roi = annual_owner_roi_after_tax if tax_mode == "after" else annual_owner_roi_before_tax
    prior_snapshots = (
        AnnualPropertySnapshot.objects.filter(property=property_obj, year__lte=snapshot.year)
        .select_related("property")
        .prefetch_related("costs")
        .order_by("year")
    )
    cumulative_cash_in = ZERO
    cumulative_operating_cash_out = ZERO
    cumulative_equity_build = ZERO
    cumulative_estimated_tax = ZERO
    for prior_snapshot in prior_snapshots:
        prior_rent = annual_rent_totals(property_obj, prior_snapshot.year)
        prior_loan = loan_metrics(property_obj, prior_snapshot.year)
        prior_owner_cold_rent = money(prior_rent.cold_rent * owner_share)
        prior_costs, _ = snapshot_operating_costs(prior_snapshot, prior_owner_cold_rent, owner_share)
        prior_cash_in = money(prior_rent.cold_rent * owner_share)
        prior_cash_out = money(prior_costs + prior_loan.interest_paid + prior_snapshot.vacancy_loss)
        cumulative_cash_in += prior_cash_in
        cumulative_operating_cash_out += prior_cash_out
        cumulative_equity_build += prior_loan.principal_paid
    cumulative_cash_in = money(cumulative_cash_in)
    cumulative_operating_cash_out = money(cumulative_operating_cash_out)
    cumulative_cash_out = money(purchase_cash_out + cumulative_operating_cash_out)
    cumulative_cashflow_before_tax = money(cumulative_cash_in - cumulative_operating_cash_out)
    cumulative_estimated_tax = money(cumulative_estimated_tax)
    cumulative_cashflow_after_tax = money(cumulative_cashflow_before_tax - cumulative_estimated_tax)
    cumulative_equity_build = money(cumulative_equity_build)
    cumulative_free_cashflow_before_tax = money(cumulative_cashflow_before_tax - cumulative_equity_build)
    cumulative_free_cashflow_after_tax = money(cumulative_cashflow_after_tax - cumulative_equity_build)
    cumulative_owner_roi_before_tax = None
    cumulative_owner_roi_after_tax = None
    if purchase_cash_out > 0:
        cumulative_owner_roi_before_tax = ratio(cumulative_cashflow_before_tax, purchase_cash_out)
        cumulative_owner_roi_after_tax = ratio(cumulative_cashflow_after_tax, purchase_cash_out)
    cumulative_cashflow = cumulative_cashflow_after_tax if tax_mode == "after" else cumulative_cashflow_before_tax
    cumulative_free_cashflow = cumulative_free_cashflow_after_tax if tax_mode == "after" else cumulative_free_cashflow_before_tax
    cumulative_owner_roi = cumulative_owner_roi_after_tax if tax_mode == "after" else cumulative_owner_roi_before_tax
    owner_equity_basis = money(
        property_obj.purchase_price * owner_share
        - loan.opening_balance
    )
    if owner_equity_basis <= 0:
        owner_equity_basis = money(owner_property_value - loan.opening_balance)
    cash_equity_roi = None
    if owner_equity_basis > 0:
        cash_equity_roi = ratio(cashflow, owner_equity_basis)
    equity_value = money(owner_property_value - loan.closing_balance)
    return PropertyPerformance(
        property=property_obj,
        year=snapshot.year,
        property_value=owner_property_value,
        annual_cold_rent=annual_cold_rent,
        annual_total_rent=annual_total_rent,
        operating_costs=costs,
        recurring_expense=recurring_expense,
        vacancy_loss=money(snapshot.vacancy_loss),
        noi=noi,
        debt_service=loan.debt_service,
        interest_paid=loan.interest_paid,
        principal_paid=loan.principal_paid,
        purchase_cash_out=purchase_cash_out,
        annual_cash_in=annual_cash_in,
        annual_cash_out=annual_cash_out,
        cashflow_before_tax=cashflow_before_tax,
        estimated_taxable_result=estimated_taxable_result,
        estimated_tax=estimated_tax,
        cashflow_after_tax=cashflow_after_tax,
        cashflow=cashflow,
        free_cashflow_before_tax=free_cashflow_before_tax,
        free_cashflow_after_tax=free_cashflow_after_tax,
        free_cashflow=free_cashflow,
        annual_equity_build=annual_equity_build,
        annual_owner_roi_before_tax=annual_owner_roi_before_tax,
        annual_owner_roi_after_tax=annual_owner_roi_after_tax,
        annual_owner_roi=annual_owner_roi,
        cumulative_cash_in=cumulative_cash_in,
        cumulative_cash_out=cumulative_cash_out,
        cumulative_cashflow_before_tax=cumulative_cashflow_before_tax,
        cumulative_estimated_tax=cumulative_estimated_tax,
        cumulative_cashflow_after_tax=cumulative_cashflow_after_tax,
        cumulative_cashflow=cumulative_cashflow,
        cumulative_free_cashflow_before_tax=cumulative_free_cashflow_before_tax,
        cumulative_free_cashflow_after_tax=cumulative_free_cashflow_after_tax,
        cumulative_free_cashflow=cumulative_free_cashflow,
        cumulative_equity_build=cumulative_equity_build,
        cumulative_owner_roi_before_tax=cumulative_owner_roi_before_tax,
        cumulative_owner_roi_after_tax=cumulative_owner_roi_after_tax,
        cumulative_owner_roi=cumulative_owner_roi,
        closing_debt=loan.closing_balance,
        owner_equity_basis=owner_equity_basis,
        equity_value=equity_value,
        gross_yield=ratio(annual_cold_rent, owner_property_value),
        net_yield=ratio(noi, owner_property_value),
        ltv=ratio(loan.closing_balance, owner_property_value),
        cash_equity_roi=cash_equity_roi,
        debt_service_coverage=ratio(noi, loan.debt_service),
    )


@dataclass(frozen=True)
class PortfolioPerformance:
    year: int
    rows: list[PropertyPerformance]
    total_value: Decimal
    total_debt: Decimal
    total_equity: Decimal
    total_rent: Decimal
    total_noi: Decimal
    total_debt_service: Decimal
    tax_calculations_enabled: bool
    tax_mode: str
    annual_tax_deductible_costs: Decimal
    portfolio_taxable_result: Decimal
    total_cashflow_before_tax: Decimal
    total_estimated_tax: Decimal
    total_cashflow_after_tax: Decimal
    total_cashflow: Decimal
    total_free_cashflow_before_tax: Decimal
    total_free_cashflow_after_tax: Decimal
    total_free_cashflow: Decimal
    total_purchase_cash_out: Decimal
    total_annual_cash_in: Decimal
    total_annual_cash_out: Decimal
    total_annual_equity_build: Decimal
    annual_owner_roi_before_tax: Decimal
    annual_owner_roi_after_tax: Decimal
    annual_owner_roi: Decimal
    total_cumulative_cash_out: Decimal
    total_cumulative_cashflow_before_tax: Decimal
    total_cumulative_estimated_tax: Decimal
    total_cumulative_cashflow_after_tax: Decimal
    total_cumulative_cashflow: Decimal
    total_cumulative_free_cashflow_before_tax: Decimal
    total_cumulative_free_cashflow_after_tax: Decimal
    total_cumulative_free_cashflow: Decimal
    total_cumulative_equity_build: Decimal
    cumulative_owner_roi_before_tax: Decimal
    cumulative_owner_roi_after_tax: Decimal
    cumulative_owner_roi: Decimal
    ltv: Decimal
    cash_equity_roi: Decimal
    net_yield: Decimal


@dataclass(frozen=True)
class DataQualityItem:
    severity: str
    message: str


@dataclass(frozen=True)
class DashboardDataQuality:
    year: int
    items: list[DataQualityItem]


def _lease_overlaps_year(lease: Lease, year_start: date, year_end: date) -> bool:
    return lease.start_date <= year_end and (lease.end_date is None or lease.end_date >= year_start)


def _lease_has_rent_for_year(lease: Lease, year_start: date, year_end: date) -> bool:
    return lease.rent_periods.filter(effective_start__lte=year_end).filter(
        Q(effective_end__isnull=True) | Q(effective_end__gte=year_start)
    ).exists()


def _snapshot_has_explicit_costs(snapshot: AnnualPropertySnapshot) -> bool:
    costs = list(snapshot.costs.all())
    return bool(costs and not all(_is_migrated_recurring_cost(cost) for cost in costs))


def dashboard_data_quality(year: int, property_ids: list[int] | None = None) -> DashboardDataQuality:
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    properties = (
        Property.objects.prefetch_related("units__leases__rent_periods", "loans__annual_snapshots", "annual_snapshots__costs")
        .order_by("name")
    )
    if property_ids:
        properties = properties.filter(pk__in=property_ids)
    properties = list(properties)
    snapshot_by_property_id = {
        snapshot.property_id: snapshot
        for snapshot in AnnualPropertySnapshot.objects.prefetch_related("costs").filter(year=year, property__in=properties)
    }

    items: list[DataQualityItem] = []
    rent_warnings = []
    loan_warnings = []
    value_warnings = []
    cost_warnings = []
    ownership_warnings = []

    for property_obj in properties:
        for unit in property_obj.units.all():
            overlapping_leases = [lease for lease in unit.leases.all() if _lease_overlaps_year(lease, year_start, year_end)]
            for lease in overlapping_leases:
                if not _lease_has_rent_for_year(lease, year_start, year_end):
                    rent_warnings.append(f"Rent history missing for {property_obj.name} / {unit.label}.")

        for loan in property_obj.loans.all():
            if not any(snapshot.year == year for snapshot in loan.annual_snapshots.all()):
                loan_warnings.append(f"Loan balance missing for {property_obj.name} / {loan.name}.")

        snapshot = snapshot_by_property_id.get(property_obj.pk)
        if snapshot is None:
            if property_obj.purchase_price:
                value_warnings.append(f"Property value missing for {property_obj.name}. Purchase price will be used.")
            else:
                value_warnings.append(f"Property value missing for {property_obj.name}. No purchase price fallback is available.")
        if property_obj.recurring_expense_amount is None and (snapshot is None or not _snapshot_has_explicit_costs(snapshot)):
            cost_warnings.append(f"Non-recoverable costs missing for {property_obj.name}. Using 5% rent estimate.")

        if property_obj.ownership_share <= ZERO:
            ownership_warnings.append(f"Ownership share missing for {property_obj.name}. Your-share KPIs may be distorted.")

    if rent_warnings:
        items.extend(DataQualityItem("warning", message) for message in rent_warnings)
    else:
        items.append(DataQualityItem("ok", "Rent history complete"))

    if loan_warnings:
        items.extend(DataQualityItem("warning", message) for message in loan_warnings)
    else:
        items.append(DataQualityItem("ok", "Loan balance entered"))

    items.extend(DataQualityItem("warning", message) for message in value_warnings)
    items.extend(DataQualityItem("warning", message) for message in cost_warnings)
    items.extend(DataQualityItem("warning", message) for message in ownership_warnings)

    return DashboardDataQuality(year=year, items=items)


@dataclass(frozen=True)
class PotentialDealMetrics:
    deal: PotentialDeal
    scenario: PotentialFinancingScenario | None
    annual_cold_rent: Decimal
    annual_total_rent: Decimal
    owner_annual_cold_rent: Decimal
    owner_annual_total_rent: Decimal
    owner_monthly_total_rent: Decimal
    operating_costs: Decimal
    owner_operating_costs: Decimal
    owner_monthly_operating_costs: Decimal
    owner_cash_out: Decimal
    annual_cash_in: Decimal
    annual_cash_out: Decimal
    cashflow: Decimal
    free_cashflow: Decimal
    annual_equity_build: Decimal
    liquidity_cashflow: Decimal
    monthly_liquidity_cashflow: Decimal
    noi: Decimal
    owner_noi: Decimal
    debt_service: Decimal
    monthly_debt_service: Decimal
    interest_cost: Decimal
    principal_repayment_estimate: Decimal
    monthly_principal_repayment_estimate: Decimal
    monthly_cashflow: Decimal
    annual_owner_roi: Decimal
    cash_on_cash_return: Decimal
    principal_repayment_return: Decimal
    gross_yield: Decimal
    net_yield: Decimal
    ltv: Decimal
    dscr: Decimal
    years_cold_rent_to_price: Decimal
    owner_value: Decimal
    owner_debt: Decimal


@dataclass(frozen=True)
class PotentialDealPortfolioComparison:
    portfolio: PortfolioPerformance
    metrics: PotentialDealMetrics
    after_cashflow: Decimal
    current_monthly_cashflow: Decimal
    after_monthly_cashflow: Decimal
    after_annual_owner_roi: Decimal
    after_debt: Decimal
    after_value: Decimal
    after_ltv: Decimal
    after_annual_rent: Decimal
    delta_cashflow: Decimal
    delta_monthly_cashflow: Decimal
    delta_annual_owner_roi: Decimal
    delta_debt: Decimal
    delta_value: Decimal
    delta_ltv: Decimal
    delta_annual_rent: Decimal


@dataclass(frozen=True)
class PotentialScenarioComparison:
    scenario: PotentialFinancingScenario
    metrics: PotentialDealMetrics
    comparison: PotentialDealPortfolioComparison
    is_highest_annual_owner_roi: bool


@dataclass(frozen=True)
class PotentialDealOptimizerOption:
    financing_ratio: Decimal
    loan_amount: Decimal
    cash_out: Decimal
    interest_rate: Decimal
    monthly_interest_cost: Decimal
    maximum_monthly_payment: Decimal
    payment_headroom: Decimal
    annual_cashflow: Decimal
    annual_owner_roi: Decimal
    owner_debt: Decimal
    is_feasible: bool
    reason: str


@dataclass(frozen=True)
class PotentialDealOptimizerResult:
    deal: PotentialDeal
    maximum_cash_out: Decimal
    fixed_buying_costs: Decimal
    maximum_financing_percent: Decimal
    maximum_monthly_payment: Decimal
    rate_100: Decimal
    rate_80: Decimal
    rate_60: Decimal
    rate_40: Decimal
    options: list[PotentialDealOptimizerOption]
    winner: PotentialDealOptimizerOption | None


def monthly(value: Decimal | int | float | None) -> Decimal:
    return money(money(value) / Decimal("12"))


def _optimizer_financing_ratios(maximum_financing_percent: Decimal) -> list[Decimal]:
    maximum_financing_percent = maximum_financing_percent.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    ratios = []
    current = Decimal("40")
    while current <= maximum_financing_percent:
        ratios.append(current)
        current += Decimal("5")
    if ratios[-1] != maximum_financing_percent:
        ratios.append(maximum_financing_percent)
    return ratios


def _interpolated_optimizer_rate(financing_ratio_percent: Decimal, rate_40: Decimal, rate_60: Decimal, rate_80: Decimal, rate_100: Decimal) -> Decimal:
    anchors = [
        (Decimal("40"), rate_40),
        (Decimal("60"), rate_60),
        (Decimal("80"), rate_80),
        (Decimal("100"), rate_100),
    ]
    for anchor_ratio, anchor_rate in anchors:
        if financing_ratio_percent == anchor_ratio:
            return anchor_rate.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    lower_ratio, lower_rate = anchors[0]
    upper_ratio, upper_rate = anchors[-1]
    for index, (anchor_ratio, anchor_rate) in enumerate(anchors[1:], start=1):
        if financing_ratio_percent < anchor_ratio:
            lower_ratio, lower_rate = anchors[index - 1]
            upper_ratio, upper_rate = anchor_ratio, anchor_rate
            break
    position = (financing_ratio_percent - lower_ratio) / (upper_ratio - lower_ratio)
    return (lower_rate + ((upper_rate - lower_rate) * position)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def optimize_potential_deal_scenario(
    deal: PotentialDeal,
    maximum_cash_out: Decimal,
    fixed_buying_costs: Decimal,
    maximum_financing_percent: Decimal,
    maximum_monthly_payment: Decimal,
    rate_100: Decimal,
    rate_80: Decimal,
    rate_60: Decimal,
    rate_40: Decimal,
) -> PotentialDealOptimizerResult:
    owner_share = deal.ownership_share
    annual_cold_rent = money(deal.expected_monthly_cold_rent * Decimal("12"))
    operating_costs = money(deal.yearly_non_recoverable_costs if deal.yearly_non_recoverable_costs is not None else annual_cold_rent * Decimal("0.05"))
    total_project_cost = money(deal.purchase_price + fixed_buying_costs)
    options = []
    for financing_ratio in _optimizer_financing_ratios(maximum_financing_percent):
        ratio_decimal = financing_ratio / Decimal("100")
        interest_rate = _interpolated_optimizer_rate(financing_ratio, rate_40, rate_60, rate_80, rate_100)
        loan_amount = money(deal.purchase_price * ratio_decimal)
        cash_out = money((total_project_cost - loan_amount) * owner_share)
        monthly_interest_cost = money(loan_amount * interest_rate / Decimal("12"))
        payment_headroom = money(maximum_monthly_payment - monthly_interest_cost)
        annual_cashflow = money((annual_cold_rent - operating_costs - (loan_amount * interest_rate)) * owner_share)
        owner_debt = money(loan_amount * owner_share)
        annual_owner_roi = ratio(annual_cashflow, cash_out)
        reason = ""
        if cash_out <= 0:
            reason = "Cash out is zero or negative"
        elif cash_out > maximum_cash_out:
            reason = "Above cash invested cap"
        elif monthly_interest_cost > maximum_monthly_payment:
            reason = "Interest exceeds payment cap"
        options.append(
            PotentialDealOptimizerOption(
                financing_ratio=financing_ratio,
                loan_amount=loan_amount,
                cash_out=cash_out,
                interest_rate=interest_rate,
                monthly_interest_cost=monthly_interest_cost,
                maximum_monthly_payment=money(maximum_monthly_payment),
                payment_headroom=payment_headroom,
                annual_cashflow=annual_cashflow,
                annual_owner_roi=annual_owner_roi,
                owner_debt=owner_debt,
                is_feasible=not reason,
                reason=reason or "Feasible",
            )
        )
    feasible_options = [option for option in options if option.is_feasible]
    winner = max(
        feasible_options,
        key=lambda option: (option.annual_owner_roi, option.payment_headroom, -option.owner_debt),
        default=None,
    )
    return PotentialDealOptimizerResult(
        deal=deal,
        maximum_cash_out=money(maximum_cash_out),
        fixed_buying_costs=money(fixed_buying_costs),
        maximum_financing_percent=maximum_financing_percent,
        maximum_monthly_payment=money(maximum_monthly_payment),
        rate_100=rate_100,
        rate_80=rate_80,
        rate_60=rate_60,
        rate_40=rate_40,
        options=options,
        winner=winner,
    )


def potential_deal_optimizer_notes(result: PotentialDealOptimizerResult) -> str:
    winner = result.winner
    if not winner:
        return ""
    return "\n".join(
        [
            "Generated by Scenario Optimizer.",
            f"Financing ratio: {winner.financing_ratio}%",
            f"Fixed buying costs: {result.fixed_buying_costs}",
            f"Maximum cash invested: {result.maximum_cash_out}",
            f"Monthly payment cap: {result.maximum_monthly_payment}",
            f"Rate anchors: 40%={result.rate_40 * Decimal('100')}%, 60%={result.rate_60 * Decimal('100')}%, 80%={result.rate_80 * Decimal('100')}%, 100%={result.rate_100 * Decimal('100')}%",
            f"Generated cash invested: {winner.cash_out}",
            f"Monthly interest cost: {winner.monthly_interest_cost}",
            f"Payment headroom: {winner.payment_headroom}",
        ]
    )


def potential_deal_metrics(deal: PotentialDeal, scenario: PotentialFinancingScenario | None = None) -> PotentialDealMetrics:
    owner_share = deal.ownership_share
    annual_cold_rent = money(deal.expected_monthly_cold_rent * Decimal("12"))
    annual_total_rent = money((deal.expected_monthly_cold_rent + deal.expected_monthly_utility_prepayment) * Decimal("12"))
    operating_costs = money(deal.yearly_non_recoverable_costs if deal.yearly_non_recoverable_costs is not None else annual_cold_rent * Decimal("0.05"))
    owner_annual_cold_rent = money(annual_cold_rent * owner_share)
    owner_annual_total_rent = money(annual_total_rent * owner_share)
    owner_operating_costs = money(operating_costs * owner_share)
    noi = money(annual_cold_rent - operating_costs)
    owner_noi = money(noi * owner_share)
    owner_value = money(deal.purchase_price * owner_share)
    debt_service = ZERO
    interest_cost = ZERO
    principal_repayment_estimate = ZERO
    owner_debt = ZERO
    if scenario:
        owner_cash_out = money(scenario.owner_cash_out)
        owner_debt = money(scenario.loan_amount * owner_share)
        debt_service = money(scenario.monthly_payment * Decimal("12") * owner_share)
        interest_cost = money(scenario.loan_amount * scenario.interest_rate * owner_share)
        principal_repayment_estimate = money(max(debt_service - interest_cost, ZERO))
    else:
        owner_cash_out = ZERO
    annual_cash_in = owner_annual_cold_rent
    liquidity_cashflow = money(annual_cash_in - owner_operating_costs - debt_service)
    annual_equity_build = principal_repayment_estimate
    annual_cash_out = money(owner_operating_costs + interest_cost)
    cashflow = money(annual_cash_in - annual_cash_out)
    free_cashflow = money(cashflow - annual_equity_build)
    annual_owner_roi = ratio(cashflow, owner_cash_out)
    cash_on_cash_return = ratio(free_cashflow, owner_cash_out)
    principal_repayment_return = ratio(annual_equity_build, owner_cash_out)
    return PotentialDealMetrics(
        deal=deal,
        scenario=scenario,
        annual_cold_rent=annual_cold_rent,
        annual_total_rent=annual_total_rent,
        owner_annual_cold_rent=owner_annual_cold_rent,
        owner_annual_total_rent=owner_annual_total_rent,
        owner_monthly_total_rent=monthly(owner_annual_total_rent),
        operating_costs=operating_costs,
        owner_operating_costs=owner_operating_costs,
        owner_monthly_operating_costs=monthly(owner_operating_costs),
        owner_cash_out=owner_cash_out,
        annual_cash_in=annual_cash_in,
        annual_cash_out=annual_cash_out,
        cashflow=cashflow,
        free_cashflow=free_cashflow,
        annual_equity_build=annual_equity_build,
        liquidity_cashflow=liquidity_cashflow,
        monthly_liquidity_cashflow=monthly(liquidity_cashflow),
        noi=noi,
        owner_noi=owner_noi,
        debt_service=debt_service,
        monthly_debt_service=monthly(debt_service),
        interest_cost=interest_cost,
        principal_repayment_estimate=principal_repayment_estimate,
        monthly_principal_repayment_estimate=monthly(principal_repayment_estimate),
        monthly_cashflow=monthly(cashflow),
        annual_owner_roi=annual_owner_roi,
        cash_on_cash_return=cash_on_cash_return,
        principal_repayment_return=principal_repayment_return,
        gross_yield=ratio(owner_annual_cold_rent, owner_value),
        net_yield=ratio(owner_noi, owner_value),
        ltv=ratio(owner_debt, owner_value),
        dscr=ratio(owner_noi, debt_service),
        years_cold_rent_to_price=ratio(deal.purchase_price, annual_cold_rent),
        owner_value=owner_value,
        owner_debt=owner_debt,
    )


def potential_deal_portfolio_comparison(deal: PotentialDeal, scenario: PotentialFinancingScenario | None, year: int | None = None) -> PotentialDealPortfolioComparison:
    portfolio = portfolio_performance(year, tax_mode="before")
    metrics = potential_deal_metrics(deal, scenario)
    current_cashflow = portfolio.total_cashflow
    after_cashflow = money(current_cashflow + metrics.cashflow)
    after_equity_build = money(portfolio.total_annual_equity_build + metrics.annual_equity_build)
    after_purchase_cash_out = money(portfolio.total_purchase_cash_out + metrics.owner_cash_out)
    after_annual_owner_roi = ratio(after_cashflow, after_purchase_cash_out)
    after_debt = money(portfolio.total_debt + metrics.owner_debt)
    after_value = money(portfolio.total_value + metrics.owner_value)
    after_ltv = ratio(after_debt, after_value)
    after_annual_rent = money(portfolio.total_rent + metrics.owner_annual_cold_rent)
    return PotentialDealPortfolioComparison(
        portfolio=portfolio,
        metrics=metrics,
        after_cashflow=after_cashflow,
        current_monthly_cashflow=monthly(current_cashflow),
        after_monthly_cashflow=monthly(after_cashflow),
        after_annual_owner_roi=after_annual_owner_roi,
        after_debt=after_debt,
        after_value=after_value,
        after_ltv=after_ltv,
        after_annual_rent=after_annual_rent,
        delta_cashflow=money(after_cashflow - current_cashflow),
        delta_monthly_cashflow=monthly(after_cashflow - current_cashflow),
        delta_annual_owner_roi=(after_annual_owner_roi - portfolio.annual_owner_roi).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
        delta_debt=money(after_debt - portfolio.total_debt),
        delta_value=money(after_value - portfolio.total_value),
        delta_ltv=(after_ltv - portfolio.ltv).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
        delta_annual_rent=money(after_annual_rent - portfolio.total_rent),
    )


def potential_deal_scenario_comparisons(deal: PotentialDeal, year: int | None = None) -> list[PotentialScenarioComparison]:
    scenarios = list(deal.scenarios.all())
    comparisons = [(scenario, potential_deal_portfolio_comparison(deal, scenario, year)) for scenario in scenarios]
    highest_annual_owner_roi_scenario_id = None
    if comparisons:
        highest_annual_owner_roi_scenario_id = max(comparisons, key=lambda item: item[1].metrics.annual_owner_roi)[0].pk
    return [
        PotentialScenarioComparison(
            scenario=scenario,
            metrics=comparison.metrics,
            comparison=comparison,
            is_highest_annual_owner_roi=scenario.pk == highest_annual_owner_roi_scenario_id,
        )
        for scenario, comparison in comparisons
    ]


def portfolio_performance(
    year: int | None = None,
    property_ids: list[int] | None = None,
    tax_mode: str = "after",
    tax_settings: AppSettings | None = None,
) -> PortfolioPerformance:
    tax_mode = normalize_tax_mode(tax_mode)
    tax_settings = tax_settings or AppSettings.load()
    tax_calculations_enabled = tax_settings.tax_calculations_enabled
    if not tax_calculations_enabled:
        tax_mode = "before"
    if year is None:
        year = (
            AnnualPropertySnapshot.objects.order_by("-year")
            .values_list("year", flat=True)
            .first()
            or date.today().year
        )
    snapshots = AnnualPropertySnapshot.objects.select_related("property").prefetch_related("costs").filter(year=year)
    if property_ids:
        snapshots = snapshots.filter(property_id__in=property_ids)
    rows = [property_performance(snapshot, tax_mode=tax_mode, tax_settings=tax_settings) for snapshot in snapshots]
    total_value = money(sum((row.property_value for row in rows), ZERO))
    total_debt = money(sum((row.closing_debt for row in rows), ZERO))
    total_equity = money(sum((row.equity_value for row in rows), ZERO))
    total_rent = money(sum((row.annual_cold_rent for row in rows), ZERO))
    total_noi = money(sum((row.noi for row in rows), ZERO))
    total_debt_service = money(sum((row.debt_service for row in rows), ZERO))
    total_cashflow_before_tax = money(sum((row.cashflow_before_tax for row in rows), ZERO))
    tax_deductible_costs = annual_tax_deductible_costs(year) if tax_calculations_enabled else ZERO
    portfolio_taxable_result = money(total_cashflow_before_tax - tax_deductible_costs)
    total_estimated_tax = (
        estimated_tax_for_result(portfolio_taxable_result, tax_settings.effective_tax_rate, tax_settings.tax_loss_benefit_enabled)
        if tax_calculations_enabled
        else ZERO
    )
    total_cashflow_after_tax = money(total_cashflow_before_tax - total_estimated_tax)
    total_cashflow = total_cashflow_after_tax if tax_mode == "after" else total_cashflow_before_tax
    total_free_cashflow_before_tax = money(sum((row.free_cashflow_before_tax for row in rows), ZERO))
    total_free_cashflow_after_tax = money(total_cashflow_after_tax - sum((row.annual_equity_build for row in rows), ZERO))
    total_free_cashflow = total_free_cashflow_after_tax if tax_mode == "after" else total_free_cashflow_before_tax
    total_purchase_cash_out = money(sum((row.purchase_cash_out for row in rows), ZERO))
    total_annual_cash_in = money(sum((row.annual_cash_in for row in rows), ZERO))
    total_annual_cash_out = money(sum((row.annual_cash_out for row in rows), ZERO))
    total_annual_equity_build = money(sum((row.annual_equity_build for row in rows), ZERO))
    annual_owner_roi_before_tax = ratio(total_cashflow_before_tax, total_purchase_cash_out)
    annual_owner_roi_after_tax = ratio(total_cashflow_after_tax, total_purchase_cash_out)
    annual_owner_roi = ratio(total_cashflow, total_purchase_cash_out)
    total_cumulative_cash_out = money(sum((row.cumulative_cash_out for row in rows), ZERO))
    total_cumulative_cashflow_before_tax = money(sum((row.cumulative_cashflow_before_tax for row in rows), ZERO))
    total_cumulative_estimated_tax = ZERO
    if tax_calculations_enabled:
        prior_year_query = AnnualPropertySnapshot.objects.filter(year__lte=year)
        if property_ids:
            prior_year_query = prior_year_query.filter(property_id__in=property_ids)
        prior_years = list(prior_year_query.order_by("year").values_list("year", flat=True).distinct())
        for prior_year in prior_years:
            prior_snapshots = AnnualPropertySnapshot.objects.select_related("property").prefetch_related("costs").filter(year=prior_year)
            if property_ids:
                prior_snapshots = prior_snapshots.filter(property_id__in=property_ids)
            prior_cashflow_before_tax = money(
                sum((property_performance(prior_snapshot).cashflow_before_tax for prior_snapshot in prior_snapshots), ZERO)
            )
            prior_taxable_result = money(prior_cashflow_before_tax - annual_tax_deductible_costs(prior_year))
            total_cumulative_estimated_tax += estimated_tax_for_result(
                prior_taxable_result,
                tax_settings.effective_tax_rate,
                tax_settings.tax_loss_benefit_enabled,
            )
    total_cumulative_estimated_tax = money(total_cumulative_estimated_tax)
    total_cumulative_cashflow_after_tax = money(sum((row.cumulative_cashflow_after_tax for row in rows), ZERO))
    if tax_calculations_enabled:
        total_cumulative_cashflow_after_tax = money(total_cumulative_cashflow_before_tax - total_cumulative_estimated_tax)
    total_cumulative_cashflow = money(sum((row.cumulative_cashflow for row in rows), ZERO))
    total_cumulative_cashflow = total_cumulative_cashflow_after_tax if tax_mode == "after" else total_cumulative_cashflow_before_tax
    total_cumulative_free_cashflow_before_tax = money(sum((row.cumulative_free_cashflow_before_tax for row in rows), ZERO))
    total_cumulative_free_cashflow_after_tax = money(total_cumulative_cashflow_after_tax - sum((row.cumulative_equity_build for row in rows), ZERO))
    total_cumulative_free_cashflow = total_cumulative_free_cashflow_after_tax if tax_mode == "after" else total_cumulative_free_cashflow_before_tax
    total_cumulative_equity_build = money(sum((row.cumulative_equity_build for row in rows), ZERO))
    cumulative_owner_roi_before_tax = ratio(total_cumulative_cashflow_before_tax, total_purchase_cash_out)
    cumulative_owner_roi_after_tax = ratio(total_cumulative_cashflow_after_tax, total_purchase_cash_out)
    cumulative_owner_roi = ratio(total_cumulative_cashflow, total_purchase_cash_out)
    total_equity_basis = money(sum((row.owner_equity_basis for row in rows), ZERO))
    return PortfolioPerformance(
        year=year,
        rows=rows,
        total_value=total_value,
        total_debt=total_debt,
        total_equity=total_equity,
        total_rent=total_rent,
        total_noi=total_noi,
        total_debt_service=total_debt_service,
        tax_calculations_enabled=tax_calculations_enabled,
        tax_mode=tax_mode,
        annual_tax_deductible_costs=tax_deductible_costs,
        portfolio_taxable_result=portfolio_taxable_result,
        total_cashflow_before_tax=total_cashflow_before_tax,
        total_estimated_tax=total_estimated_tax,
        total_cashflow_after_tax=total_cashflow_after_tax,
        total_cashflow=total_cashflow,
        total_free_cashflow_before_tax=total_free_cashflow_before_tax,
        total_free_cashflow_after_tax=total_free_cashflow_after_tax,
        total_free_cashflow=total_free_cashflow,
        total_purchase_cash_out=total_purchase_cash_out,
        total_annual_cash_in=total_annual_cash_in,
        total_annual_cash_out=total_annual_cash_out,
        total_annual_equity_build=total_annual_equity_build,
        annual_owner_roi_before_tax=annual_owner_roi_before_tax,
        annual_owner_roi_after_tax=annual_owner_roi_after_tax,
        annual_owner_roi=annual_owner_roi,
        total_cumulative_cash_out=total_cumulative_cash_out,
        total_cumulative_cashflow_before_tax=total_cumulative_cashflow_before_tax,
        total_cumulative_estimated_tax=total_cumulative_estimated_tax,
        total_cumulative_cashflow_after_tax=total_cumulative_cashflow_after_tax,
        total_cumulative_cashflow=total_cumulative_cashflow,
        total_cumulative_free_cashflow_before_tax=total_cumulative_free_cashflow_before_tax,
        total_cumulative_free_cashflow_after_tax=total_cumulative_free_cashflow_after_tax,
        total_cumulative_free_cashflow=total_cumulative_free_cashflow,
        total_cumulative_equity_build=total_cumulative_equity_build,
        cumulative_owner_roi_before_tax=cumulative_owner_roi_before_tax,
        cumulative_owner_roi_after_tax=cumulative_owner_roi_after_tax,
        cumulative_owner_roi=cumulative_owner_roi,
        ltv=ratio(total_debt, total_value),
        cash_equity_roi=ratio(total_cashflow, total_equity_basis),
        net_yield=ratio(total_noi, total_value),
    )


def available_years(property_ids: list[int] | None = None) -> list[int]:
    snapshots = AnnualPropertySnapshot.objects
    if property_ids:
        snapshots = snapshots.filter(property_id__in=property_ids)
    return list(snapshots.order_by("-year").values_list("year", flat=True).distinct())


def _property_history_start_year(property_obj: Property) -> int:
    candidates = []
    if property_obj.acquisition_date:
        candidates.append(property_obj.acquisition_date.year)
    snapshot_year = property_obj.annual_snapshots.order_by("year").values_list("year", flat=True).first()
    if snapshot_year:
        candidates.append(snapshot_year)
    loan_start_year = property_obj.loans.exclude(start_date__isnull=True).order_by("start_date").values_list("start_date", flat=True).first()
    if loan_start_year:
        candidates.append(loan_start_year.year)
    loan_snapshot_year = (
        AnnualLoanSnapshot.objects.filter(loan__property=property_obj)
        .order_by("year")
        .values_list("year", flat=True)
        .first()
    )
    if loan_snapshot_year:
        candidates.append(loan_snapshot_year)
    return min(candidates) if candidates else date.today().year


def latest_portfolio_history_year() -> int:
    candidates = [date.today().year]
    snapshot_year = AnnualPropertySnapshot.objects.order_by("-year").values_list("year", flat=True).first()
    if snapshot_year:
        candidates.append(snapshot_year)
    loan_snapshot_year = AnnualLoanSnapshot.objects.order_by("-year").values_list("year", flat=True).first()
    if loan_snapshot_year:
        candidates.append(loan_snapshot_year)
    return max(candidates)


def backfill_property_snapshots(property_obj: Property | None = None, through_year: int | None = None) -> int:
    properties = Property.objects.all()
    if property_obj is not None:
        properties = properties.filter(pk=property_obj.pk)
    through_year = through_year or latest_portfolio_history_year()
    created = 0
    for item in properties:
        start_year = _property_history_start_year(item)
        if start_year > through_year:
            continue
        for year in range(start_year, through_year + 1):
            _, was_created = AnnualPropertySnapshot.objects.get_or_create(
                property=item,
                year=year,
                defaults={
                    "property_value": item.purchase_price,
                    "valuation_source": "Default purchase price",
                },
            )
            if was_created:
                created += 1
    return created
