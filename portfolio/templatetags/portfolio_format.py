from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def eur(value):
    value = Decimal(value or 0)
    return f"€{value:,.2f}"


@register.filter
def eur0(value):
    value = Decimal(value or 0)
    return f"€{value:,.0f}"


@register.filter
def pct(value):
    value = Decimal(value or 0)
    return f"{value:.2%}"


@register.filter
def signed_eur(value):
    value = Decimal(value or 0)
    sign = "+" if value > 0 else ""
    return f"{sign}€{value:,.2f}"


@register.filter
def signed_pct(value):
    value = Decimal(value or 0)
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2%}"


@register.filter
def pct_or_na(value):
    if value is None:
        return "n/a"
    value = Decimal(value)
    return f"{value:.2%}"
