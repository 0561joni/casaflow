from __future__ import annotations

import html
import mimetypes
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, connection
from django.db.models import Prefetch
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.safestring import mark_safe
from django.utils.text import slugify
from django.views.generic import CreateView, ListView, UpdateView
from pypdf.errors import PdfReadError

from .exports import (
    bank_financing_preview,
    bank_financing_pdf,
    create_database_backup,
    export_bank_financing_workbook,
    restore_database_backup,
)
from .forms import (
    AnnualLoanSnapshotForm,
    AnnualPropertyCostForm,
    AnnualPropertySnapshotForm,
    AnnualPortfolioTaxSettingsForm,
    AppSettingsForm,
    DatabaseRestoreForm,
    LeaseForm,
    LeasePeopleForm,
    PotentialDealCreateForm,
    PotentialDealForm,
    PotentialDealOptimizerForm,
    PotentialFinancingScenarioForm,
    PropertyCreateForm,
    PropertyHistoryTableForm,
    PropertyDossierForm,
    RentChangeForm,
    RentPeriodForm,
    TenantForm,
    TenantChangeForm,
    UnitAdministrationForm,
    UnitCurrentInfoForm,
    UnitWithTenantForm,
    UnitForm,
    LoanBalanceTableForm,
    MietbescheinigungForm,
    WorkbookImportForm,
    ensure_primary_lease_person,
    sync_lease_start_from_rent_periods,
)
from .importer import import_master_immos
from .mietbescheinigung import mietbescheinigung_pdf
from .models import AnnualPortfolioTax, AppSettings, AnnualLoanSnapshot, AnnualPropertySnapshot, LandlordProfile, Lease, LeasePerson, Loan, PotentialDeal, PotentialFinancingScenario, Property, RentPeriod, ReportExport, Tenant, Unit
from .services import available_years, dashboard_data_quality, loan_performance_rows, money, optimize_potential_deal_scenario, portfolio_performance, potential_deal_metrics, potential_deal_optimizer_notes, potential_deal_portfolio_comparison, potential_deal_scenario_comparisons, property_performance, property_unit_overviews, ratio, unit_rent_overview


REFERENCE_DOCUMENT = Path(settings.BASE_DIR) / "docs" / "casaflow_reference.md"
REFERENCE_DOCUMENT_DE = Path(settings.BASE_DIR) / "docs" / "casaflow_reference_de.md"


def _fallback_markdown(markdown_text: str) -> str:
    lines = markdown_text.splitlines()
    blocks = []
    in_code = False
    in_list = False
    code_lines = []

    def close_list():
        nonlocal in_list
        if in_list:
            blocks.append("</ul>")
            in_list = False

    for raw_line in lines:
        line = raw_line.rstrip()
        if line.startswith("```"):
            if in_code:
                blocks.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
                code_lines = []
                in_code = False
            else:
                close_list()
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        if not line:
            close_list()
            continue
        heading_match = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading_match:
            close_list()
            level = len(heading_match.group(1))
            blocks.append(f"<h{level}>{html.escape(heading_match.group(2))}</h{level}>")
            continue
        if line.startswith("- "):
            if not in_list:
                blocks.append("<ul>")
                in_list = True
            blocks.append(f"<li>{html.escape(line[2:])}</li>")
            continue
        close_list()
        blocks.append(f"<p>{html.escape(line)}</p>")
    close_list()
    return "\n".join(blocks)


def _render_reference_markdown(markdown_text: str) -> str:
    try:
        import markdown as markdown_lib
    except ModuleNotFoundError:
        return _fallback_markdown(markdown_text)
    return markdown_lib.markdown(markdown_text, extensions=["extra", "sane_lists"])


@login_required
def reference_page(request):
    reference_document = REFERENCE_DOCUMENT_DE if getattr(request, "casaflow_language_code", "en") == "de" and REFERENCE_DOCUMENT_DE.exists() else REFERENCE_DOCUMENT
    if not reference_document.exists():
        raise Http404
    markdown_text = reference_document.read_text(encoding="utf-8")
    return render(
        request,
        "portfolio/reference.html",
        {
            "reference_html": mark_safe(_render_reference_markdown(markdown_text)),
            "reference_path": reference_document,
        },
    )


@login_required
def dashboard(request):
    tax_settings = AppSettings.load()
    tax_calculations_enabled = tax_settings.tax_calculations_enabled
    tax_mode = "before" if not tax_calculations_enabled or request.GET.get("tax") == "before" else "after"
    all_properties = list(Property.objects.order_by("name"))
    valid_property_ids = {property_obj.pk for property_obj in all_properties}
    requested_property_ids = []
    for raw_id in request.GET.getlist("properties") + request.GET.getlist("property"):
        try:
            property_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if property_id in valid_property_ids and property_id not in requested_property_ids:
            requested_property_ids.append(property_id)
    selected_property_ids = requested_property_ids
    selected_property_set = set(selected_property_ids)
    filtered_property_ids = selected_property_ids or None
    years = available_years(filtered_property_ids)
    selected_year = int(request.GET.get("year") or (years[0] if years else date.today().year))
    if years and selected_year not in years:
        selected_year = years[0]
    portfolio = portfolio_performance(selected_year, filtered_property_ids, tax_mode=tax_mode, tax_settings=tax_settings)
    data_quality = dashboard_data_quality(selected_year, filtered_property_ids)
    data_quality_warnings = [item for item in data_quality.items if item.severity == "warning"]
    trend_years = sorted(years)
    trend_portfolios = [portfolio_performance(year, filtered_property_ids, tax_mode=tax_mode, tax_settings=tax_settings) for year in trend_years]
    trend_breakdowns = {"cashflow": [], "debt": [], "ltv": [], "value": []}
    for year, trend_portfolio in zip(trend_years, trend_portfolios):
        property_rows = sorted(trend_portfolio.rows, key=lambda row: row.property.name)
        trend_breakdowns["cashflow"].append(
            [
                {"label": row.property.name, "value": float(row.cashflow)}
                for row in property_rows
            ]
        )
        trend_breakdowns["value"].append(
            [
                {"label": row.property.name, "value": float(row.property_value)}
                for row in property_rows
            ]
        )
        trend_breakdowns["ltv"].append(
            [
                {
                    "label": row.property.name,
                    "debt": float(row.closing_debt),
                    "value": float(row.property_value),
                    "ltv": float(row.ltv * 100),
                }
                for row in property_rows
            ]
        )
        loan_snapshots = AnnualLoanSnapshot.objects.select_related("loan", "loan__property").filter(year=year)
        if filtered_property_ids:
            loan_snapshots = loan_snapshots.filter(loan__property_id__in=filtered_property_ids)
        trend_breakdowns["debt"].append(
            [
                {
                    "label": f"{snapshot.loan.property.name} - {snapshot.loan.name}",
                    "value": float(money(snapshot.closing_balance * snapshot.loan.property.ownership_share)),
                }
                for snapshot in loan_snapshots.order_by("loan__property__name", "loan__name")
            ]
        )
    chart_data = {
        "labels": [row.property.name for row in portfolio.rows],
        "roi": [float((row.annual_owner_roi or 0) * 100) for row in portfolio.rows],
        "ltv": [float(row.ltv * 100) for row in portfolio.rows],
        "cashflow": [float(row.cashflow) for row in portfolio.rows],
        "trend": {
            "labels": trend_years,
            "metrics": {
                "cashflow": [float(row.total_cashflow) for row in trend_portfolios],
                "debt": [float(row.total_debt) for row in trend_portfolios],
                "ltv": [float(row.ltv * 100) for row in trend_portfolios],
                "value": [float(row.total_value) for row in trend_portfolios],
            },
            "breakdowns": trend_breakdowns,
        },
        "valueDebt": {
            "labels": ["Value", "Debt", "Equity"],
            "values": [float(portfolio.total_value), float(portfolio.total_debt), float(portfolio.total_equity)],
            "series": [
                {
                    "label": row.property.name,
                    "value": float(row.property_value),
                    "debt": float(row.closing_debt),
                    "equity": float(row.equity_value),
                }
                for row in portfolio.rows
            ],
        },
    }
    selected_property_names = [property_obj.name for property_obj in all_properties if property_obj.pk in selected_property_set]
    property_filter_label = (
        ", ".join(selected_property_names)
        if 0 < len(selected_property_names) <= 2
        else f"{len(selected_property_names)} properties selected"
        if selected_property_names
        else "All properties"
    )
    return render(
        request,
        "portfolio/dashboard.html",
        {
            "portfolio": portfolio,
            "data_quality": data_quality,
            "data_quality_warnings": data_quality_warnings,
            "years": years,
            "selected_year": selected_year,
            "chart_data": chart_data,
            "all_properties": all_properties,
            "selected_property_ids": selected_property_ids,
            "selected_property_set": selected_property_set,
            "property_filter_label": property_filter_label,
            "tax_mode": tax_mode,
            "tax_badge_label": "Before tax" if tax_mode == "before" else "After tax estimate",
            "tax_settings": tax_settings,
            "tax_calculations_enabled": tax_calculations_enabled,
        },
    )


class PropertyListView(LoginRequiredMixin, ListView):
    model = Property
    template_name = "portfolio/property_list.html"
    context_object_name = "properties"

    def get_queryset(self):
        return Property.objects.prefetch_related("units__leases__tenant", "units__leases__rent_periods", "loans")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        property_cards = []
        for property_obj in context["properties"]:
            unit_overviews = property_unit_overviews(property_obj)
            active_units = sum(1 for row in unit_overviews if row.active_lease)
            vacant_units = len(unit_overviews) - active_units
            property_cards.append(
                {
                    "property": property_obj,
                    "unit_count": len(unit_overviews),
                    "active_units": active_units,
                    "vacant_units": vacant_units,
                    "loan_count": property_obj.loans.count(),
                }
            )
        context.update({"property_cards": property_cards})
        return context


@login_required
def property_detail(request, pk):
    property_obj = get_object_or_404(
        Property.objects.select_related("administration").prefetch_related("units__leases__tenant", "units__leases__rent_periods", "loans"),
        pk=pk,
    )
    unit_overviews = property_unit_overviews(property_obj)
    edit_mode = request.GET.get("edit") == "1"
    if request.method == "POST":
        if request.POST.get("form_kind") == "notes":
            property_obj.notes = request.POST.get("notes", "")
            property_obj.save(update_fields=["notes", "updated_at"])
            messages.success(request, "Saved")
            return redirect("property_detail", pk=property_obj.pk)
        else:
            form = PropertyDossierForm(request.POST, request.FILES, instance=property_obj)
            if form.is_valid():
                form.save()
                messages.success(request, "Saved")
                return redirect("property_detail", pk=property_obj.pk)
            edit_mode = True
            messages.error(request, "Save failed. Please check the highlighted fields.")
    else:
        form = PropertyDossierForm(instance=property_obj)
    return render(
        request,
        "portfolio/property_detail.html",
        {
            "property": property_obj,
            "unit_overviews": unit_overviews,
            "form": form,
            "edit_mode": edit_mode,
        },
    )


@login_required
def property_create(request):
    if request.method == "POST":
        form = PropertyCreateForm(request.POST, request.FILES)
        if form.is_valid():
            property_obj = form.save()
            messages.success(request, "Saved")
            return redirect("property_detail", pk=property_obj.pk)
        else:
            messages.error(request, "Save failed. Please check the highlighted fields.")
    else:
        form = PropertyCreateForm(initial={"ownership_share": "1.000000"})
    return render(request, "portfolio/property_create_form.html", {"form": form, "title": "Add Property"})


@login_required
def property_update(request, pk):
    property_obj = get_object_or_404(Property, pk=pk)
    years = available_years()
    selected_year = int(request.POST.get("selected_year") or request.GET.get("year") or (years[0] if years else date.today().year))
    if request.method == "POST":
        form = PropertyHistoryTableForm(request.POST, property_obj=property_obj, selected_year=selected_year)
        if form.is_valid():
            try:
                property_obj = form.save()
                messages.success(request, "Saved")
                return redirect("property_detail", pk=property_obj.pk)
            except IntegrityError:
                messages.error(request, "Save failed because yearly property data could not be written consistently. Please check the table values and try again.")
        else:
            messages.error(request, "Save failed. Please check the highlighted fields.")
    else:
        form = PropertyHistoryTableForm(property_obj=property_obj, selected_year=selected_year)
    return render(request, "portfolio/property_form.html", {"form": form, "title": f"Edit {property_obj.name}", "property": property_obj, "selected_year": selected_year})


def _property_from_request(request):
    property_id = request.POST.get("property") or request.GET.get("property")
    return get_object_or_404(Property, pk=property_id) if property_id else None


def _rent_history_redirect(property_obj):
    if property_obj:
        return redirect("property_detail", pk=property_obj.pk)
    return redirect("property_list")


def _lease_people_summary(lease):
    role_labels = dict(LeasePerson.ROLES)
    links = list(lease.people.select_related("person").all())
    people = [
        {
            "person": link.person,
            "name": str(link.person),
            "role": link.role,
            "role_label": link.get_role_display(),
            "move_in_date": link.move_in_date,
            "move_out_date": link.move_out_date,
            "notes": link.notes,
            "is_fallback": False,
        }
        for link in links
    ]
    if not people and lease.tenant_id:
        people = [
            {
                "person": lease.tenant,
                "name": str(lease.tenant),
                "role": LeasePerson.PRIMARY,
                "role_label": role_labels[LeasePerson.PRIMARY],
                "move_in_date": lease.start_date,
                "move_out_date": lease.end_date,
                "notes": "",
                "is_fallback": True,
            }
        ]
    contract_people = [item for item in people if item["role"] in LeasePerson.CONTRACT_ROLES]
    other_people = [item for item in people if item["role"] not in LeasePerson.CONTRACT_ROLES]
    return {"lease": lease, "people": people, "contract_people": contract_people, "other_people": other_people}


def _split_address(address: str) -> tuple[str, str, str]:
    lines = [line.strip() for line in (address or "").splitlines() if line.strip()]
    if not lines:
        return "", "", ""
    one_line = " ".join(lines)
    match = re.match(r"^(?P<street>.*?),\s*(?P<zip>\d{4,5})\s+(?P<city>.+)$", one_line)
    if match:
        return match.group("street").strip(), match.group("zip"), match.group("city").strip()
    if len(lines) >= 2:
        match = re.match(r"^(?P<zip>\d{4,5})\s+(?P<city>.+)$", lines[1])
        if match:
            return lines[0], match.group("zip"), match.group("city").strip()
    return lines[0], "", ""


def _property_address_parts(property_obj) -> tuple[str, str, str]:
    if property_obj.street_address or property_obj.postal_code or property_obj.city:
        return property_obj.street_address, property_obj.postal_code, property_obj.city
    return _split_address(property_obj.address)


def _contract_people_for_lease(lease):
    if not lease:
        return []
    if not lease.people.exists() and lease.tenant_id:
        ensure_primary_lease_person(lease)
    summary = _lease_people_summary(lease)
    return summary["contract_people"]


def _landlord_initial(profile):
    if not profile:
        return {
            "landlord_name": "",
            "landlord_street": "",
            "landlord_zip": "",
            "landlord_city": "",
            "landlord_phone": "",
            "landlord_fax": "",
            "landlord_email": "",
            "include_signature": False,
        }
    return {
        "landlord_profile": str(profile.pk),
        "landlord_name": profile.name,
        "landlord_street": profile.street_address,
        "landlord_zip": profile.postal_code,
        "landlord_city": profile.city,
        "landlord_phone": profile.phone,
        "landlord_fax": profile.fax,
        "landlord_email": profile.email,
        "include_signature": bool(profile.signature_image),
    }


def _mietbescheinigung_initial(unit, overview, selected_template, landlord_profile):
    contract_people = _contract_people_for_lease(overview.active_lease)
    tenants = [item["person"] for item in contract_people]
    tenant_name = ", ".join(str(tenant) for tenant in tenants)
    tenant_contact_parts = []
    for tenant in tenants:
        contact = " / ".join(part for part in [tenant.phone, tenant.email] if part)
        if contact:
            tenant_contact_parts.append(contact)
    tenant_street, tenant_zip, tenant_city = _property_address_parts(unit.property)
    administration = getattr(unit.property, "administration", None)
    rent = overview.current_rent
    today = date.today()
    initial = {
        "template": selected_template,
        "tenant_name": tenant_name,
        "tenant_street": tenant_street,
        "tenant_zip": tenant_zip,
        "tenant_city": tenant_city,
        "tenant_contact": "; ".join(tenant_contact_parts),
        "lease_start": overview.active_lease.start_date if overview.active_lease else None,
        "tenant_count": len(contract_people),
        "floor": unit.floor,
        "construction_year": administration.construction_year if administration else None,
        "building_area_sqm": administration.total_building_area_sqm if administration else None,
        "living_area_sqm": unit.area_sqm,
        "rent_valid_from": rent.effective_start if rent else (overview.active_lease.start_date if overview.active_lease else today),
        "cold_rent": overview.cold_rent,
        "operating_costs": overview.utility_prepayment,
        "total_rent": overview.total_rent,
        "operating_costs_advance": True,
        "issue_date": today,
    }
    initial.update(_landlord_initial(landlord_profile))
    initial["issue_place"] = initial.get("landlord_city", "")
    return initial


def _mietbescheinigung_source_warnings(unit, overview, contract_people):
    warnings = []
    if not overview.active_lease:
        warnings.append("This unit has no active tenant period.")
    if overview.active_lease and not contract_people:
        warnings.append("This unit has no active contract tenant.")
    if overview.active_lease and not overview.active_lease.start_date:
        warnings.append("The active tenant period has no lease start date.")
    return warnings


def _selected_landlord_profile(raw_id: str | None):
    profiles = list(LandlordProfile.objects.order_by("-is_default", "name"))
    if raw_id and raw_id != "__new__":
        return next((profile for profile in profiles if str(profile.pk) == str(raw_id)), profiles[0] if profiles else None)
    if raw_id == "__new__":
        return None
    return profiles[0] if profiles else None


TENANT_ROLE_OPTIONS = [
    ("contract", "Contract tenants"),
    (LeasePerson.PRIMARY, "Primary"),
    (LeasePerson.CO_TENANT, "Co-contract tenant"),
    (LeasePerson.OCCUPANT, "Occupant"),
    (LeasePerson.CHILD, "Child"),
    (LeasePerson.OTHER, "Other"),
    ("everyone", "Everyone"),
]
TENANT_STATUS_OPTIONS = [
    ("current", "Current"),
    ("former", "Former"),
    ("everyone", "Everyone"),
]
TENANT_SORTS = {
    "name": lambda row: row["name"].lower(),
    "email": lambda row: row["tenant"].email.lower(),
    "phone": lambda row: row["tenant"].phone.lower(),
    "property": lambda row: row["property_name"].lower(),
    "unit": lambda row: row["unit_label"].lower(),
    "role": lambda row: row["role_label"].lower(),
    "status": lambda row: row["status"].lower(),
    "cold_rent": lambda row: row["cold_rent"],
    "total_rent": lambda row: row["total_rent"],
}


def _lease_is_current(lease, as_of):
    return lease.is_active and lease.start_date <= as_of and (lease.end_date is None or lease.end_date >= as_of)


def _association_is_current(association, as_of):
    lease = association["lease"]
    return (
        _lease_is_current(lease, as_of)
        and association["move_in_date"] <= as_of
        and (association["move_out_date"] is None or association["move_out_date"] >= as_of)
    )


def _rent_period_for_association(association, as_of):
    rent_periods = list(association["lease"].rent_periods.all())
    current_periods = [
        period
        for period in rent_periods
        if period.effective_start <= as_of and (period.effective_end is None or period.effective_end >= as_of)
    ]
    if current_periods:
        return sorted(current_periods, key=lambda period: period.effective_start, reverse=True)[0]
    if rent_periods:
        return sorted(rent_periods, key=lambda period: period.effective_start, reverse=True)[0]
    return None


def _tenant_association_search_text(association):
    parts = [
        association["property_name"],
        association["unit_label"],
        association["role_label"],
    ]
    return " ".join(part for part in parts if part).lower()


def _tenant_directory_rows(request):
    today = date.today()
    role_filter = request.GET.get("role") or "contract"
    if role_filter not in {value for value, _label in TENANT_ROLE_OPTIONS}:
        role_filter = "contract"
    status_filter = request.GET.get("status") or "current"
    if status_filter not in {value for value, _label in TENANT_STATUS_OPTIONS}:
        status_filter = "current"
    property_filter = request.GET.get("property") or ""
    search = (request.GET.get("q") or "").strip().lower()
    sort = request.GET.get("sort") or "name"
    sort_desc = sort.startswith("-")
    sort_key = sort[1:] if sort_desc else sort
    if sort_key not in TENANT_SORTS:
        sort = "name"
        sort_desc = False
        sort_key = "name"

    lease_qs = Lease.objects.select_related("unit", "unit__property", "tenant").prefetch_related(
        "people",
        "rent_periods",
    )
    link_qs = LeasePerson.objects.select_related("lease", "lease__unit", "lease__unit__property", "person").prefetch_related(
        "lease__rent_periods",
    )
    tenants = Tenant.objects.prefetch_related(
        Prefetch("lease_links", queryset=link_qs),
        Prefetch("leases", queryset=lease_qs),
    )
    role_labels = dict(LeasePerson.ROLES)
    rows = []
    for tenant in tenants:
        associations = []
        for link in tenant.lease_links.all():
            unit = link.lease.unit
            associations.append(
                {
                    "lease": link.lease,
                    "unit": unit,
                    "property": unit.property,
                    "property_name": unit.property.name,
                    "unit_label": unit.label,
                    "role": link.role,
                    "role_label": link.get_role_display(),
                    "move_in_date": link.move_in_date,
                    "move_out_date": link.move_out_date,
                    "notes": link.notes,
                    "is_fallback": False,
                }
            )
        for lease in tenant.leases.all():
            if list(lease.people.all()):
                continue
            unit = lease.unit
            associations.append(
                {
                    "lease": lease,
                    "unit": unit,
                    "property": unit.property,
                    "property_name": unit.property.name,
                    "unit_label": unit.label,
                    "role": LeasePerson.PRIMARY,
                    "role_label": role_labels[LeasePerson.PRIMARY],
                    "move_in_date": lease.start_date,
                    "move_out_date": lease.end_date,
                    "notes": "",
                    "is_fallback": True,
                }
            )
        if not associations:
            continue
        current_associations = [association for association in associations if _association_is_current(association, today)]
        status = "Current" if current_associations else "Former"
        if status_filter == "current" and not current_associations:
            continue
        if status_filter == "former" and current_associations:
            continue
        if role_filter == "contract":
            if not any(association["role"] in LeasePerson.CONTRACT_ROLES for association in associations):
                continue
        elif role_filter != "everyone" and not any(association["role"] == role_filter for association in associations):
            continue
        if property_filter:
            try:
                property_id = int(property_filter)
            except ValueError:
                property_id = None
            if property_id and not any(association["property"].pk == property_id for association in associations):
                continue
        search_text = " ".join(
            [
                str(tenant),
                tenant.email,
                tenant.phone,
                tenant.support_office_name,
                tenant.support_office_email,
                tenant.support_office_phone,
                tenant.relationship_notes,
                tenant.notes,
                *[_tenant_association_search_text(association) for association in associations],
            ]
        ).lower()
        if search and search not in search_text:
            continue
        primary_association = sorted(
            current_associations or associations,
            key=lambda association: (association["move_in_date"], association["property_name"], association["unit_label"]),
            reverse=True,
        )[0]
        primary_rent = _rent_period_for_association(primary_association, today)
        cold_rent = money(primary_rent.cold_rent if primary_rent else 0)
        total_rent = money(primary_rent.total_rent if primary_rent else 0)
        rows.append(
            {
                "tenant": tenant,
                "name": str(tenant),
                "status": status,
                "associations": sorted(associations, key=lambda association: association["move_in_date"], reverse=True),
                "primary_association": primary_association,
                "property_name": primary_association["property_name"],
                "unit_label": primary_association["unit_label"],
                "role_label": primary_association["role_label"],
                "cold_rent": cold_rent,
                "total_rent": total_rent,
            }
        )
    rows.sort(key=TENANT_SORTS[sort_key], reverse=sort_desc)
    return {
        "rows": rows,
        "role_filter": role_filter,
        "status_filter": status_filter,
        "property_filter": property_filter,
        "search": request.GET.get("q") or "",
        "sort": sort,
        "sort_key": sort_key,
        "sort_desc": sort_desc,
    }


def _sort_url(request, field):
    query = request.GET.copy()
    current_sort = request.GET.get("sort") or "name"
    query["sort"] = f"-{field}" if current_sort == field else field
    return f"?{query.urlencode()}"


@login_required
def tenant_list(request):
    directory = _tenant_directory_rows(request)
    properties = Property.objects.order_by("name")
    sort_urls = {field: _sort_url(request, field) for field in TENANT_SORTS}
    return render(
        request,
        "portfolio/tenant_list.html",
        {
            **directory,
            "properties": properties,
            "role_options": TENANT_ROLE_OPTIONS,
            "status_options": TENANT_STATUS_OPTIONS,
            "sort_urls": sort_urls,
            "current_path": request.get_full_path(),
        },
    )


@login_required
def unit_create(request):
    property_obj = _property_from_request(request)
    if not property_obj:
        messages.error(request, "Choose a property before adding a unit.")
        return redirect("property_list")
    if request.method == "POST":
        form = UnitWithTenantForm(request.POST, property_obj=property_obj)
        if form.is_valid():
            unit = form.save()
            messages.success(request, "Saved")
            return redirect("unit_detail", pk=unit.pk)
        messages.error(request, "Save failed. Please check the highlighted fields.")
    else:
        form = UnitWithTenantForm(property_obj=property_obj)
    return render(request, "portfolio/unit_with_tenant_form.html", {"form": form, "title": f"Add Unit to {property_obj.name}", "property": property_obj, "cancel_url": reverse("property_detail", kwargs={"pk": property_obj.pk})})


@login_required
def unit_detail(request, pk):
    unit = get_object_or_404(
        Unit.objects.select_related("property", "property__administration", "administration", "land_registry", "technical_info").prefetch_related("leases__tenant", "leases__people__person", "leases__rent_periods", "contacts__contact"),
        pk=pk,
    )
    leases = unit.leases.select_related("tenant").prefetch_related("rent_periods", "people__person").order_by("-start_date")
    lease_summaries = [_lease_people_summary(lease) for lease in leases]
    overview = unit_rent_overview(unit)
    if overview.active_lease and not overview.active_lease.people.exists():
        ensure_primary_lease_person(overview.active_lease)
    active_summary = _lease_people_summary(overview.active_lease) if overview.active_lease else None
    edit_mode = request.GET.get("edit") == "1"
    if request.method == "POST":
        info_form = UnitCurrentInfoForm(request.POST, unit=unit, active_lease=overview.active_lease, current_rent_period=overview.current_rent)
        people_form = LeasePeopleForm(request.POST, lease=overview.active_lease) if overview.active_lease else None
        info_valid = info_form.is_valid()
        people_valid = people_form.is_valid() if people_form else True
        if info_valid and people_valid:
            info_form.save()
            if people_form:
                people_form.save()
            messages.success(request, "Saved")
            return redirect("unit_detail", pk=unit.pk)
        edit_mode = True
        messages.error(request, "Save failed. Please check the highlighted fields.")
    else:
        info_form = UnitCurrentInfoForm(unit=unit, active_lease=overview.active_lease, current_rent_period=overview.current_rent)
        people_form = LeasePeopleForm(lease=overview.active_lease) if overview.active_lease else None
    return render(
        request,
        "portfolio/unit_detail.html",
        {
            "unit": unit,
            "property": unit.property,
            "overview": overview,
            "leases": leases,
            "lease_summaries": lease_summaries,
            "active_summary": active_summary,
            "info_form": info_form,
            "people_form": people_form,
            "edit_mode": edit_mode,
        },
    )


@login_required
def unit_mietbescheinigung(request, pk):
    unit = get_object_or_404(
        Unit.objects.select_related("property", "property__administration").prefetch_related("leases__tenant", "leases__people__person", "leases__rent_periods"),
        pk=pk,
    )
    overview = unit_rent_overview(unit)
    contract_people = _contract_people_for_lease(overview.active_lease)
    landlord_profiles = list(LandlordProfile.objects.order_by("-is_default", "name"))
    selected_template = request.POST.get("template") or request.GET.get("template") or "jobcenter"
    selected_landlord = _selected_landlord_profile(request.POST.get("landlord_profile") or request.GET.get("landlord"))
    initial = _mietbescheinigung_initial(unit, overview, selected_template, selected_landlord)
    if request.GET.get("landlord") == "__new__":
        initial["landlord_profile"] = "__new__"
    source_warnings = _mietbescheinigung_source_warnings(unit, overview, contract_people)

    if request.method == "POST":
        form = MietbescheinigungForm(request.POST, request.FILES, landlord_profiles=landlord_profiles)
        if form.is_valid():
            cleaned = form.cleaned_data
            action = request.POST.get("action") or "generate"
            missing_fields = []
            if not cleaned.get("landlord_name"):
                missing_fields.append("Landlord name is required.")
            if not cleaned.get("landlord_street"):
                missing_fields.append("Landlord street / address is required.")

            if missing_fields:
                for error in missing_fields:
                    form.add_error(None, error)
                messages.error(request, "Save failed. Please complete the landlord fields.")
            elif action == "save_landlord":
                landlord = LandlordProfile.objects.create(
                    name=cleaned["landlord_name"],
                    street_address=cleaned["landlord_street"],
                    postal_code=cleaned.get("landlord_zip", ""),
                    city=cleaned.get("landlord_city", ""),
                    phone=cleaned.get("landlord_phone", ""),
                    fax=cleaned.get("landlord_fax", ""),
                    email=cleaned.get("landlord_email", ""),
                    signature_image=cleaned.get("signature_image"),
                    is_default=not LandlordProfile.objects.exists(),
                )
                messages.success(request, "Landlord saved.")
                return redirect(f"{reverse('unit_mietbescheinigung', kwargs={'pk': unit.pk})}?template={cleaned['template']}&landlord={landlord.pk}")
            elif source_warnings:
                for error in source_warnings + missing_fields:
                    form.add_error(None, error)
                messages.error(request, "Generation failed. Please complete the required data first.")
            else:
                pdf_data = dict(cleaned)
                signature_upload = cleaned.get("signature_image")
                if cleaned.get("include_signature"):
                    if signature_upload:
                        pdf_data["signature_bytes"] = signature_upload.read()
                    elif selected_landlord and selected_landlord.signature_image:
                        pdf_data["signature_path"] = selected_landlord.signature_image.path
                try:
                    pdf_bytes = mietbescheinigung_pdf(cleaned["template"], pdf_data)
                except (FileNotFoundError, PdfReadError, OSError):
                    form.add_error(None, "PDF generation failed because the selected template file could not be loaded.")
                    messages.error(request, "Generation failed. The selected PDF template could not be loaded.")
                else:
                    unit_slug = slugify(f"{unit.property.name}-{unit.label}") or f"unit-{unit.pk}"
                    file_name = f"mietbescheinigung-{cleaned['template']}-{unit_slug}-{date.today().isoformat()}.pdf"
                    _save_export_file(pdf_bytes, file_name)
                    ReportExport.objects.update_or_create(
                        export_type="mietbescheinigung_pdf",
                        file_name=file_name,
                        defaults={
                            "title": f"Mietbescheinigung {unit.label}",
                            "property": unit.property,
                        },
                    )
                    response = HttpResponse(pdf_bytes, content_type="application/pdf")
                    response["Content-Disposition"] = f'attachment; filename="{file_name}"'
                    return response
        else:
            messages.error(request, "Generation failed. Please check the highlighted fields.")
    else:
        form = MietbescheinigungForm(initial=initial, landlord_profiles=landlord_profiles)
    if not (selected_landlord and selected_landlord.signature_image):
        form.fields["include_signature"].widget.attrs["disabled"] = "disabled"

    return render(
        request,
        "portfolio/mietbescheinigung_form.html",
        {
            "form": form,
            "unit": unit,
            "property": unit.property,
            "overview": overview,
            "landlord_profiles": landlord_profiles,
            "selected_landlord": selected_landlord,
            "source_warnings": source_warnings,
            "cancel_url": reverse("unit_detail", kwargs={"pk": unit.pk}),
        },
    )


@login_required
def unit_update(request, pk):
    unit = get_object_or_404(Unit.objects.select_related("property"), pk=pk)
    if request.method == "POST":
        form = UnitForm(request.POST, instance=unit, property_obj=unit.property)
        if form.is_valid():
            form.save()
            messages.success(request, "Saved")
            return redirect("unit_detail", pk=unit.pk)
        messages.error(request, "Save failed. Please check the highlighted fields.")
    else:
        form = UnitForm(instance=unit, property_obj=unit.property)
    return render(request, "portfolio/form.html", {"form": form, "title": f"Edit {unit.label}", "cancel_url": reverse("unit_detail", kwargs={"pk": unit.pk})})


@login_required
def unit_administration_update(request, pk):
    unit = get_object_or_404(Unit.objects.select_related("property").prefetch_related("contacts__contact"), pk=pk)
    if request.method == "POST":
        form = UnitAdministrationForm(request.POST, unit=unit)
        if form.is_valid():
            form.save()
            messages.success(request, "Saved")
            return redirect("unit_detail", pk=unit.pk)
        messages.error(request, "Save failed. Please check the highlighted fields.")
    else:
        form = UnitAdministrationForm(unit=unit)
    return render(request, "portfolio/unit_administration_form.html", {"form": form, "unit": unit, "property": unit.property, "title": f"Edit Administration for {unit.label}", "cancel_url": reverse("unit_detail", kwargs={"pk": unit.pk})})


class TenantCreateView(LoginRequiredMixin, CreateView):
    form_class = TenantForm
    template_name = "portfolio/form.html"
    success_url = reverse_lazy("property_list")


@login_required
def tenant_update(request, pk):
    tenant = get_object_or_404(Tenant, pk=pk)
    next_url = request.POST.get("next") or request.GET.get("next") or reverse("property_list")
    if request.method == "POST":
        form = TenantForm(request.POST, instance=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, "Saved")
            return redirect(next_url)
        messages.error(request, "Save failed. Please check the highlighted fields.")
    else:
        form = TenantForm(instance=tenant)
    return render(request, "portfolio/form.html", {"form": form, "title": f"Edit {tenant}", "cancel_url": next_url})


@login_required
def lease_people_update(request, pk):
    lease = get_object_or_404(
        Lease.objects.select_related("unit", "unit__property", "tenant").prefetch_related("people__person"),
        pk=pk,
    )
    if request.method == "POST":
        form = LeasePeopleForm(request.POST, lease=lease)
        if form.is_valid():
            form.save()
            messages.success(request, "Saved")
            return redirect(f"{reverse('unit_detail', kwargs={'pk': lease.unit_id})}#history")
        messages.error(request, "Save failed. Please check the highlighted fields.")
    else:
        form = LeasePeopleForm(lease=lease)
    return render(request, "portfolio/lease_people_form.html", {"form": form, "lease": lease, "unit": lease.unit, "property": lease.unit.property, "cancel_url": f"{reverse('unit_detail', kwargs={'pk': lease.unit_id})}#history"})


@login_required
def unit_change_tenant(request, pk):
    unit = get_object_or_404(Unit.objects.select_related("property").prefetch_related("leases__tenant", "leases__rent_periods"), pk=pk)
    if request.method == "POST":
        form = TenantChangeForm(request.POST, unit=unit)
        if form.is_valid():
            form.save()
            messages.success(request, "Saved")
            return redirect("unit_detail", pk=unit.pk)
        messages.error(request, "Save failed. Please check the highlighted fields.")
    else:
        form = TenantChangeForm(unit=unit)
    return render(request, "portfolio/tenant_change_form.html", {"form": form, "unit": unit, "property": unit.property, "title": f"Change Tenant for {unit.label}", "cancel_url": reverse("unit_detail", kwargs={"pk": unit.pk})})


@login_required
def lease_create(request):
    property_obj = _property_from_request(request)
    unit = get_object_or_404(Unit, pk=request.POST.get("unit") or request.GET.get("unit")) if (request.POST.get("unit") or request.GET.get("unit")) else None
    if unit:
        property_obj = unit.property
    if request.method == "POST":
        form = LeaseForm(request.POST, property_obj=property_obj, unit=unit)
        if form.is_valid():
            lease = form.save()
            messages.success(request, "Saved")
            return _rent_history_redirect(lease.unit.property)
        messages.error(request, "Save failed. Please check the highlighted fields.")
    else:
        form = LeaseForm(property_obj=property_obj, unit=unit)
    return render(request, "portfolio/form.html", {"form": form, "title": "Add Lease", "cancel_url": reverse("property_detail", kwargs={"pk": property_obj.pk}) if property_obj else reverse("property_list")})


@login_required
def rent_period_create(request):
    property_obj = _property_from_request(request)
    lease = get_object_or_404(Lease, pk=request.POST.get("lease") or request.GET.get("lease")) if (request.POST.get("lease") or request.GET.get("lease")) else None
    if lease:
        property_obj = lease.unit.property
    if request.method == "POST":
        form = RentChangeForm(request.POST, lease=lease) if lease else RentPeriodForm(request.POST, property_obj=property_obj)
        if form.is_valid():
            rent_period = form.save()
            messages.success(request, "Saved")
            return redirect("unit_detail", pk=rent_period.lease.unit_id)
        messages.error(request, "Save failed. Please check the highlighted fields.")
    else:
        form = RentChangeForm(lease=lease) if lease else RentPeriodForm(property_obj=property_obj)
    title = f"Add Rent Change for {lease.unit.label}" if lease else "Add Rent Period"
    cancel_url = reverse("unit_detail", kwargs={"pk": lease.unit_id}) if lease else reverse("property_detail", kwargs={"pk": property_obj.pk}) if property_obj else reverse("property_list")
    return render(request, "portfolio/rent_change_form.html" if lease else "portfolio/form.html", {"form": form, "title": title, "lease": lease, "unit": lease.unit if lease else None, "cancel_url": cancel_url})


@login_required
def rent_period_update(request, pk):
    rent_period = get_object_or_404(RentPeriod.objects.select_related("lease__unit__property"), pk=pk)
    property_obj = rent_period.lease.unit.property
    if request.method == "POST":
        form = RentPeriodForm(request.POST, instance=rent_period, property_obj=property_obj)
        if form.is_valid():
            rent_period = form.save()
            messages.success(request, "Saved")
            return redirect("unit_detail", pk=rent_period.lease.unit_id)
        messages.error(request, "Save failed. Please check the highlighted fields.")
    else:
        form = RentPeriodForm(instance=rent_period, property_obj=property_obj)
    return render(request, "portfolio/form.html", {"form": form, "title": "Edit Rent Period", "cancel_url": reverse("unit_detail", kwargs={"pk": rent_period.lease.unit_id})})


@login_required
def rent_period_delete(request, pk):
    rent_period = get_object_or_404(RentPeriod.objects.select_related("lease__unit__property"), pk=pk)
    unit = rent_period.lease.unit
    if request.method == "POST":
        lease = rent_period.lease
        rent_period.delete()
        sync_lease_start_from_rent_periods(lease)
        messages.success(request, "Saved")
        return redirect(f"{reverse('unit_detail', kwargs={'pk': unit.pk})}#history")
    return render(
        request,
        "portfolio/confirm_delete.html",
        {
            "title": "Delete Rent Period",
            "object_name": f"{unit.label}: {rent_period.effective_start:%d.%m.%Y}",
            "description": "This permanently deletes this historical rent record. Dashboard and rent calculations will use the remaining rent history.",
            "cancel_url": f"{reverse('unit_detail', kwargs={'pk': unit.pk})}#history",
        },
    )


class AnnualPropertySnapshotCreateView(LoginRequiredMixin, CreateView):
    form_class = AnnualPropertySnapshotForm
    template_name = "portfolio/form.html"
    success_url = reverse_lazy("dashboard")


class AnnualPropertySnapshotUpdateView(LoginRequiredMixin, UpdateView):
    model = AnnualPropertySnapshot
    form_class = AnnualPropertySnapshotForm
    template_name = "portfolio/form.html"
    success_url = reverse_lazy("dashboard")


class AnnualPropertyCostCreateView(LoginRequiredMixin, CreateView):
    form_class = AnnualPropertyCostForm
    template_name = "portfolio/form.html"
    success_url = reverse_lazy("dashboard")


@login_required
def loan_list(request):
    years = available_years()
    selected_year = int(request.GET.get("year") or (years[0] if years else date.today().year))
    rows = loan_performance_rows(selected_year)
    totals = {
        "opening_balance": money(sum((row.opening_balance for row in rows), 0)),
        "closing_balance": money(sum((row.closing_balance for row in rows), 0)),
        "current_debt": money(sum((row.current_debt for row in rows), 0)),
        "interest_paid": money(sum((row.interest_paid for row in rows), 0)),
        "principal_paid": money(sum((row.principal_paid for row in rows), 0)),
        "debt_service": money(sum((row.debt_service for row in rows), 0)),
    }
    totals["effective_interest_rate"] = ratio(totals["interest_paid"], totals["opening_balance"])
    totals["amortization_rate"] = ratio(totals["principal_paid"], totals["opening_balance"])
    return render(
        request,
        "portfolio/loan_list.html",
        {
            "rows": rows,
            "years": years,
            "selected_year": selected_year,
            "totals": totals,
            "loans_without_snapshot": Loan.objects.exclude(annual_snapshots__year=selected_year),
        },
    )


@login_required
def loan_create(request):
    years = available_years()
    selected_year = int(request.POST.get("selected_year") or request.GET.get("year") or (years[0] if years else date.today().year))
    if request.method == "POST":
        form = LoanBalanceTableForm(request.POST, selected_year=selected_year)
        if form.is_valid():
            form.save()
            messages.success(request, "Saved")
            return redirect(f"{reverse('loan_list')}?year={selected_year}")
        messages.error(request, "Save failed. Please check the highlighted fields.")
    else:
        form = LoanBalanceTableForm(selected_year=selected_year)
    return render(request, "portfolio/loan_form.html", {"form": form, "title": "Add Loan", "selected_year": selected_year})


@login_required
def loan_update(request, pk):
    loan = get_object_or_404(Loan, pk=pk)
    years = available_years()
    selected_year = int(request.POST.get("selected_year") or request.GET.get("year") or (years[0] if years else date.today().year))
    if request.method == "POST":
        form = LoanBalanceTableForm(request.POST, loan=loan, selected_year=selected_year)
        if form.is_valid():
            form.save()
            messages.success(request, "Saved")
            return redirect(f"{reverse('loan_list')}?year={selected_year}")
        messages.error(request, "Save failed. Please check the highlighted fields.")
    else:
        form = LoanBalanceTableForm(loan=loan, selected_year=selected_year)
    return render(request, "portfolio/loan_form.html", {"form": form, "title": f"Edit {loan.name}", "loan": loan, "selected_year": selected_year})


@login_required
def loan_snapshot_create(request):
    return redirect("loan_list")


@login_required
def loan_snapshot_update(request, pk):
    snapshot = get_object_or_404(AnnualLoanSnapshot, pk=pk)
    return redirect(f"{reverse('loan_update', kwargs={'pk': snapshot.loan_id})}?year={snapshot.year}")


def _selected_deal_comparison_year(request):
    years = available_years()
    try:
        selected_year = int(request.GET.get("year") or (years[0] if years else date.today().year))
    except (TypeError, ValueError):
        selected_year = years[0] if years else date.today().year
    if years and selected_year not in years:
        selected_year = years[0]
    return selected_year, years


def _selected_deal_scenario(deal, request):
    scenarios = list(deal.scenarios.all())
    requested_id = request.GET.get("scenario")
    if requested_id:
        for scenario in scenarios:
            if str(scenario.pk) == str(requested_id):
                return scenario
    for scenario in scenarios:
        if scenario.is_default:
            return scenario
    return scenarios[0] if scenarios else None


def _delta_class(value, positive_is_good=True):
    value = money(value)
    if value == 0:
        return "delta-neutral"
    is_positive = value > 0
    return "delta-positive" if is_positive == positive_is_good else "delta-negative"


def _ratio_delta_class(value, positive_is_good=True):
    if value == 0:
        return "delta-neutral"
    is_positive = value > 0
    return "delta-positive" if is_positive == positive_is_good else "delta-negative"


def _bar_width(value, max_value):
    max_value = abs(max_value)
    if not max_value:
        return "0"
    return f"{min((abs(value) / max_value) * 100, 100):.2f}"


def _potential_deal_decision_context(comparison, scenario_rows, selected_scenario):
    selected_row = next((row for row in scenario_rows if selected_scenario and row.scenario.pk == selected_scenario.pk), None)
    portfolio = comparison.portfolio
    zero = money(0)
    current_cashflow = portfolio.total_cashflow
    bar_specs = [
        ("Annual Owner ROI", portfolio.annual_owner_roi, comparison.after_annual_owner_roi, True, "Annual Owner ROI before and after adding the deal. Higher is better.", False),
        ("Portfolio Value", portfolio.total_value, comparison.after_value, False, "Ownership-share portfolio value before and after adding the deal. Higher value is shown as positive.", False),
        ("Cashflow", current_cashflow, comparison.after_cashflow, False, "Cashflow before and after adding the selected scenario. In Deals this includes equity build and subtracts interest, not principal.", True),
        ("Debt", portfolio.total_debt, comparison.after_debt, False, "Ownership-share debt before and after adding the deal. Higher debt is shown as risk.", False),
    ]
    impact_bars = []
    for label, current, after, percent, tooltip, periodic in bar_specs:
        risk = label == "Debt"
        delta = after - current
        base_value = min(abs(current), abs(after))
        stack_total = base_value + abs(delta)
        impact_bars.append(
            {
                "label": label,
                "current": current,
                "after": after,
                "delta": delta,
                "percent": percent,
                "periodic": periodic,
                "current_monthly": comparison.current_monthly_cashflow if label == "Cashflow" else None,
                "after_monthly": comparison.after_monthly_cashflow if label == "Cashflow" else None,
                "delta_monthly": comparison.delta_monthly_cashflow if label == "Cashflow" else None,
                "base_width": _bar_width(base_value, stack_total),
                "change_width": _bar_width(abs(delta), stack_total),
                "delta_class": _delta_class(delta, positive_is_good=not risk),
                "tooltip": tooltip,
            }
        )
    max_cashflow = max([abs(row.metrics.cashflow) for row in scenario_rows] + [zero])
    max_roi = max([abs(row.metrics.annual_owner_roi) for row in scenario_rows] + [zero])
    max_debt = max([abs(row.metrics.owner_debt) for row in scenario_rows] + [zero])
    max_cash_out = max([abs(row.metrics.owner_cash_out) for row in scenario_rows] + [zero])
    scenario_cards = []
    for row in scenario_rows:
        return_total = abs(row.metrics.cash_on_cash_return) + abs(row.metrics.principal_repayment_return)
        scenario_cards.append(
            {
                "row": row,
                "selected": bool(selected_scenario and row.scenario.pk == selected_scenario.pk),
                "cashflow_width": _bar_width(row.metrics.cashflow, max_cashflow),
                "roi_width": _bar_width(row.metrics.annual_owner_roi, max_roi),
                "debt_width": _bar_width(row.metrics.owner_debt, max_debt),
                "cash_out_width": _bar_width(row.metrics.owner_cash_out, max_cash_out),
                "cashflow_class": _delta_class(row.metrics.cashflow),
                "cash_on_cash_return_width": _bar_width(row.metrics.cash_on_cash_return, return_total),
                "principal_return_width": _bar_width(row.metrics.principal_repayment_return, return_total),
                "cash_on_cash_return_class": _ratio_delta_class(row.metrics.cash_on_cash_return),
                "principal_return_class": _ratio_delta_class(row.metrics.principal_repayment_return),
            }
        )
    return {
        "impact_bars": impact_bars,
        "scenario_cards": scenario_cards,
        "selected_scenario_row": selected_row,
    }


@login_required
def potential_deal_list(request):
    selected_year, years = _selected_deal_comparison_year(request)
    deals = PotentialDeal.objects.prefetch_related("scenarios")
    rows = []
    for deal in deals:
        scenario = _selected_deal_scenario(deal, request)
        rows.append({"deal": deal, "scenario": scenario, "metrics": potential_deal_metrics(deal, scenario)})
    return render(request, "portfolio/potential_deal_list.html", {"rows": rows, "selected_year": selected_year, "years": years})


@login_required
def potential_deal_detail(request, pk):
    selected_year, years = _selected_deal_comparison_year(request)
    deal = get_object_or_404(PotentialDeal.objects.prefetch_related("scenarios"), pk=pk)
    scenario = _selected_deal_scenario(deal, request)
    comparison = potential_deal_portfolio_comparison(deal, scenario, selected_year)
    scenario_rows = potential_deal_scenario_comparisons(deal, selected_year)
    decision_context = _potential_deal_decision_context(comparison, scenario_rows, scenario)
    return render(
        request,
        "portfolio/potential_deal_detail.html",
        {
            "deal": deal,
            "selected_scenario": scenario,
            "comparison": comparison,
            "scenario_rows": scenario_rows,
            **decision_context,
            "selected_year": selected_year,
            "years": years,
        },
    )


@login_required
def potential_deal_create(request):
    if request.method == "POST":
        form = PotentialDealCreateForm(request.POST)
        if form.is_valid():
            deal = form.save()
            messages.success(request, "Saved")
            scenario = deal.scenarios.filter(is_default=True).first()
            if scenario:
                return redirect(f"{reverse('potential_deal_detail', kwargs={'pk': deal.pk})}?scenario={scenario.pk}")
            return redirect("potential_deal_detail", pk=deal.pk)
        messages.error(request, "Save failed. Please check the highlighted fields.")
    else:
        form = PotentialDealCreateForm(initial={"ownership_share": "1.000000"})
    return render(request, "portfolio/potential_deal_create_form.html", {"form": form, "title": "Add Deal"})


@login_required
def potential_deal_update(request, pk):
    deal = get_object_or_404(PotentialDeal, pk=pk)
    if request.method == "POST":
        form = PotentialDealForm(request.POST, instance=deal)
        if form.is_valid():
            deal = form.save()
            messages.success(request, "Saved")
            return redirect("potential_deal_detail", pk=deal.pk)
        messages.error(request, "Save failed. Please check the highlighted fields.")
    else:
        form = PotentialDealForm(instance=deal)
    return render(request, "portfolio/potential_deal_form.html", {"form": form, "title": f"Edit {deal.name}", "deal": deal})


@login_required
def potential_scenario_create(request, deal_pk):
    deal = get_object_or_404(PotentialDeal, pk=deal_pk)
    is_first_scenario = not deal.scenarios.exists()
    if request.method == "POST":
        form = PotentialFinancingScenarioForm(request.POST, deal=deal)
        if form.is_valid():
            scenario = form.save()
            if is_first_scenario and not scenario.is_default:
                scenario.is_default = True
                scenario.save(update_fields=["is_default", "updated_at"])
            messages.success(request, "Saved")
            return redirect(f"{reverse('potential_deal_detail', kwargs={'pk': deal.pk})}?scenario={scenario.pk}")
        messages.error(request, "Save failed. Please check the highlighted fields.")
    else:
        form = PotentialFinancingScenarioForm(deal=deal, initial={"is_default": is_first_scenario})
    return render(request, "portfolio/potential_scenario_form.html", {"form": form, "title": f"Add Financing Scenario", "deal": deal})


@login_required
def potential_scenario_update(request, pk):
    scenario = get_object_or_404(PotentialFinancingScenario.objects.select_related("deal"), pk=pk)
    if request.method == "POST":
        form = PotentialFinancingScenarioForm(request.POST, instance=scenario, deal=scenario.deal)
        if form.is_valid():
            scenario = form.save()
            messages.success(request, "Saved")
            return redirect(f"{reverse('potential_deal_detail', kwargs={'pk': scenario.deal.pk})}?scenario={scenario.pk}")
        messages.error(request, "Save failed. Please check the highlighted fields.")
    else:
        form = PotentialFinancingScenarioForm(instance=scenario, deal=scenario.deal)
    return render(request, "portfolio/potential_scenario_form.html", {"form": form, "title": f"Edit {scenario.name}", "deal": scenario.deal, "scenario": scenario})


@login_required
def potential_scenario_delete(request, pk):
    scenario = get_object_or_404(PotentialFinancingScenario.objects.select_related("deal"), pk=pk)
    deal = scenario.deal
    if request.method == "POST":
        was_default = scenario.is_default
        scenario.delete()
        if was_default:
            next_default = deal.scenarios.order_by("-is_default", "name").first()
            if next_default:
                next_default.is_default = True
                next_default.save(update_fields=["is_default", "updated_at"])
        messages.success(request, "Deleted")
        return redirect("potential_deal_detail", pk=deal.pk)
    return render(
        request,
        "portfolio/confirm_delete.html",
        {
            "title": "Delete Scenario",
            "object_name": f"{deal.name}: {scenario.name}",
            "description": "This permanently deletes this financing scenario. The deal itself and other scenarios remain unchanged.",
            "cancel_url": reverse("potential_scenario_update", kwargs={"pk": scenario.pk}),
        },
    )


@login_required
def potential_deal_optimizer(request, pk):
    deal = get_object_or_404(PotentialDeal.objects.prefetch_related("scenarios"), pk=pk)
    scenario = _selected_deal_scenario(deal, request)
    initial = {
        "maximum_cash_out": scenario.owner_cash_out if scenario else None,
        "maximum_monthly_payment": scenario.monthly_payment if scenario else None,
        "fixed_buying_costs": deal.buying_costs,
        "maximum_financing_percent": "100",
        "rate_100": scenario.interest_rate if scenario else Decimal("0.050000"),
    }
    result = None
    generated_rate_fields = []
    if request.method == "POST":
        form = PotentialDealOptimizerForm(request.POST)
        if form.is_valid():
            generated_rate_fields = getattr(form, "generated_rate_fields", [])
            result = optimize_potential_deal_scenario(
                deal=deal,
                maximum_cash_out=form.cleaned_data["maximum_cash_out"],
                fixed_buying_costs=form.cleaned_data["fixed_buying_costs"],
                maximum_financing_percent=form.cleaned_data["maximum_financing_percent"],
                maximum_monthly_payment=form.cleaned_data["maximum_monthly_payment"],
                rate_100=form.cleaned_data["rate_100"],
                rate_80=form.cleaned_data["rate_80"],
                rate_60=form.cleaned_data["rate_60"],
                rate_40=form.cleaned_data["rate_40"],
            )
            if request.POST.get("action") == "save":
                scenario_name = form.cleaned_data.get("scenario_name", "").strip()
                if not result.winner:
                    messages.error(request, "No feasible optimizer result to save.")
                elif not scenario_name:
                    form.add_error("scenario_name", "Enter a name before saving the optimized scenario.")
                    messages.error(request, "Save failed. Please name the scenario.")
                else:
                    optimized_scenario = PotentialFinancingScenario.objects.create(
                        deal=deal,
                        name=scenario_name,
                        owner_cash_out=result.winner.cash_out,
                        loan_amount=result.winner.loan_amount,
                        interest_rate=result.winner.interest_rate,
                        monthly_payment=result.maximum_monthly_payment,
                        notes=potential_deal_optimizer_notes(result),
                    )
                    messages.success(request, "Optimized scenario saved.")
                    return redirect(f"{reverse('potential_deal_detail', kwargs={'pk': deal.pk})}?scenario={optimized_scenario.pk}")
        else:
            messages.error(request, "Optimization failed. Please check the highlighted fields.")
    else:
        form = PotentialDealOptimizerForm(initial=initial)
    return render(
        request,
        "portfolio/potential_deal_optimizer.html",
        {
            "deal": deal,
            "form": form,
            "result": result,
            "selected_scenario": scenario,
            "generated_rate_fields": generated_rate_fields,
        },
    )


@login_required
def import_workbook(request):
    if request.method == "POST":
        form = WorkbookImportForm(request.POST, request.FILES)
        if form.is_valid():
            import_run = import_master_immos(form.cleaned_data["workbook"], form.cleaned_data["year"])
            messages.success(request, f"Imported workbook with {len(import_run.warnings)} warning(s).")
            return redirect("dashboard")
    else:
        form = WorkbookImportForm(initial={"year": date.today().year})
    return render(request, "portfolio/import.html", {"form": form})


@login_required
def exports_page(request):
    bank_preview = bank_financing_preview(date.today())
    return render(
        request,
        "portfolio/exports.html",
        {
            "bank_preview": bank_preview,
            "years": available_years(),
            "exports": ReportExport.objects.all()[:20],
            "export_dir": Path(settings.MEDIA_ROOT) / "exports",
        },
    )


@login_required
def backup_page(request):
    return render(
        request,
        "portfolio/backup.html",
        {
            "restore_form": DatabaseRestoreForm(),
            "backup_dir": settings.APP_BACKUP_DIR,
            "backups": ReportExport.objects.filter(export_type="backup")[:20],
        },
    )


@login_required
def settings_page(request):
    app_settings = AppSettings.load()
    tax_years = sorted(
        set(available_years()) | set(AnnualPortfolioTax.objects.values_list("year", flat=True)) | {date.today().year},
        reverse=True,
    )
    tax_rows_were_visible = app_settings.tax_calculations_enabled
    if request.method == "POST":
        form = AppSettingsForm(request.POST, instance=app_settings)
        tax_form = AnnualPortfolioTaxSettingsForm(request.POST, years=tax_years)
        tax_form_required = tax_rows_were_visible and request.POST.get("tax_calculations_enabled") == "on"
        tax_form_valid = tax_form.is_valid() if tax_form_required else True
        if form.is_valid() and tax_form_valid:
            app_settings = form.save()
            if tax_form_required:
                tax_form.save()
            messages.success(request, "Saved")
            return redirect("settings")
        messages.error(request, "Save failed. Please check the highlighted fields.")
    else:
        form = AppSettingsForm(instance=app_settings)
        tax_form = AnnualPortfolioTaxSettingsForm(years=tax_years)
    return render(
        request,
        "portfolio/settings.html",
        {
            "form": form,
            "tax_form": tax_form,
            "tax_years": tax_years,
            "show_tax_details": app_settings.tax_calculations_enabled,
            "database_path": connection.settings_dict["NAME"],
            "media_root": settings.MEDIA_ROOT,
            "backup_dir": settings.APP_BACKUP_DIR,
        },
    )


@login_required
def export_bank_financing_pdf(request):
    today = date.today()
    return _download(request, bank_financing_pdf(today), f"bank-financing-overview-{today.isoformat()}.pdf", "application/pdf")


@login_required
def export_bank_financing_excel(request):
    today = date.today()
    return _download(request, export_bank_financing_workbook(today), f"bank-financing-overview-{today.isoformat()}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@login_required
def export_file(request, file_name):
    safe_name = Path(file_name).name
    if safe_name != file_name:
        raise Http404
    path = _saved_export_path(safe_name)
    if not path.exists():
        raise Http404
    content_type = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    response = FileResponse(path.open("rb"), content_type=content_type)
    response["Content-Disposition"] = f'inline; filename="{safe_name}"'
    return response


@login_required
def create_backup(request):
    if request.method != "POST":
        raise Http404
    path = create_database_backup()
    messages.success(request, f"Database backup created: {path}")
    return redirect("backup")


@login_required
def restore_backup(request):
    if request.method != "POST":
        raise Http404
    form = DatabaseRestoreForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            path = restore_database_backup(form.cleaned_data["backup_file"])
            messages.success(request, f"Database restored from uploaded backup. Staged copy: {path}")
        except ValueError as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, "Backup restore failed. Confirm replacement and upload a SQLite backup.")
    return redirect("backup")


def _saved_export_path(file_name: str) -> Path:
    return Path(settings.MEDIA_ROOT) / "exports" / Path(file_name).name


def _save_export_file(content: bytes, file_name: str) -> Path:
    path = _saved_export_path(file_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _download(request, content: bytes, file_name: str, content_type: str) -> HttpResponse:
    if request.GET.get("save"):
        path = _save_export_file(content, file_name)
        messages.success(request, f"Generated {file_name}. Open it from Recent Exports below.")
        return redirect("exports")
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{file_name}"'
    return response
