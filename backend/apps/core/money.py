"""Money helpers.

Decision D1: prices are stored tax-inclusive (Colombian retail convention), so
the tax is *extracted* from the price rather than added to it. Amounts are
Decimal with 2 places internally; COP has no cents in practice, so document
totals are rounded to whole pesos at the boundary.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

CENTS = Decimal("0.01")
ONE = Decimal("1")
HUNDRED = Decimal("100")


def money(value) -> Decimal:
    """Quantize any numeric value to 2 decimal places, half-up."""
    return Decimal(value).quantize(CENTS, rounding=ROUND_HALF_UP)


def round_to_currency_unit(value, decimals: int = 0) -> Decimal:
    """Round to the smallest unit actually circulating for the currency.

    COP uses 0 decimals; a currency with cents would pass decimals=2.
    """
    exp = Decimal(1).scaleb(-decimals)
    return Decimal(value).quantize(exp, rounding=ROUND_HALF_UP)


def split_tax_from_gross(gross, tax_rate) -> tuple[Decimal, Decimal]:
    """Split a tax-inclusive amount into (taxable base, tax amount).

    `tax_rate` is a percentage: 19 for 19% IVA, 0 for exempt.
    """
    gross = Decimal(gross)
    rate = Decimal(tax_rate)
    if rate == 0:
        return money(gross), Decimal("0.00")
    base = gross / (ONE + rate / HUNDRED)
    base = money(base)
    return base, money(gross - base)
